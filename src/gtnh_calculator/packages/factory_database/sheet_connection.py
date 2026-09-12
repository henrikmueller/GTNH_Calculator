from __future__ import annotations
import logging
import sys
import json
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st
import traceback
from typing import Callable, Mapping, cast, get_type_hints
from frozendict import frozendict
from dataclasses import dataclass, fields

from ..database_extraction.gtnh_database import GTNHDatabase
from .database import AbstractFactoryDatabase, FactoryDatabase, EmptyFactoryDatabase
from ..streamlit.streamlit_functions import confirm_action
from .constants import GID, SHEET_ID
from ..utility.general_utility import str_to_float_with_exception
from .sheets import SHEET_METADATA, SheetType, Sheet, SheetEntry

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class SheetReadingResponse:
    sheet: Sheet
    success: bool
    message: str


@dataclass(frozen=True)
class ReadingResponse:
    factory_database: AbstractFactoryDatabase
    success: bool
    message: str

    @classmethod
    def create(cls, responses: Mapping[SheetType, SheetReadingResponse]) -> ReadingResponse:
        success = all(response.success for response in responses.values())
        if success:
            message = "Successfully read all sheet entries."
            sheets = frozendict({
                sheet_type: r.sheet for sheet_type, r in responses.items()
            })
            database = FactoryDatabase(sheets=sheets)
        else:
            message = " | ".join(f'{sheet}: {response.message}' for sheet, response in responses.items() if not response.success)
            database = EmptyFactoryDatabase()
        return ReadingResponse(
            factory_database=database,
            success=success,
            message=message
        )


@dataclass(frozen=True)
class WritingResponse:
    success: bool
    message: str
    display: bool = True


def _sheet_url(gid: GID) -> str:
    return f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}'


def _read_sheet_entries(
    sheet_type: SheetType,
) -> SheetReadingResponse:
    gid = SHEET_METADATA[sheet_type].gid
    entry_type = SHEET_METADATA[sheet_type].entry_type
    df = pd.read_csv(_sheet_url(gid))
    type_hints = get_type_hints(entry_type)

    column_types = {
        f.name: cast(Callable[[object], object], type_hints[f.name])
        for f in fields(entry_type)
    }

    try:
        entries = tuple(
            entry_type(
                **{
                    name: (
                        str_to_float_with_exception(row[name])
                        if column_types[name] is float and isinstance(row[name], str)
                        else column_types[name](row[name])
                    )
                    for name in column_types
                }
            )
            for _, row in df.iterrows()
        )
        sheet = Sheet[entry_type](metadata=SHEET_METADATA[sheet_type], entries=entries)
    except Exception as e:
        return SheetReadingResponse(
            sheet=Sheet[entry_type](metadata=SHEET_METADATA[sheet_type], entries=tuple()),
            success=False,
            message=f"Failed to read sheet entries: {e}. "
                    f"Make sure that the columns in the sheet match the expected data type."
        )
    return SheetReadingResponse(
        sheet=sheet,
        success=True,
        message="Successfully read sheet entries."
    )


def _write_database_entries(
    spreadsheet: gspread.Spreadsheet, entries_per_sheet: Mapping[SheetType, tuple[SheetEntry, ...]],
) -> WritingResponse:
    total_written = 0
    for sheet_type, entries in entries_per_sheet.items():
        gid = SHEET_METADATA[sheet_type].gid
        rows_to_write = [
            [getattr(entry, f.name) for f in fields(entry)] for entry in entries
        ]
        if not rows_to_write:
            continue

        try:
            worksheet = spreadsheet.get_worksheet_by_id(int(gid))
            table_range = f"'{worksheet.title}'!A1"
            spreadsheet.values_append(
                table_range,
                params={
                    "valueInputOption": "USER_ENTERED",
                    "insertDataOption": "INSERT_ROWS",
                },
                body={
                    "values": rows_to_write,
                },
            )
            _LOGGER.info(
                "✓ Wrote %d row(s) to %s",
                len(rows_to_write),
                worksheet.title,
            )

        except Exception as e:
            _LOGGER.error("Could not write to sheet %s: %s", gid, e)

            return WritingResponse(
                success=False,
                message=f"Could not write to sheet {sheet_type}: {e}",
            )
        total_written += len(rows_to_write)

    return WritingResponse(
        success=True,
        message=f"Wrote {total_written} new row(s).",
    )


def _non_existing_entries(
    new_entries: tuple[SheetEntry, ...], existing_entries: tuple[SheetEntry, ...]
) -> tuple[SheetEntry, ...]:
    non_existing = [
        entry for entry in new_entries
        if not any(
            entry.is_duplicate_of(existing)
            for existing in existing_entries
        )
    ]
    return tuple(non_existing)


def _duplicate_entries(
    new_entries: tuple[SheetEntry, ...], existing_entries: tuple[SheetEntry, ...]
) -> tuple[SheetEntry, ...]:
    duplicate = [
        entry for entry in new_entries
        if any(
            entry.is_duplicate_of(existing)
            for existing in existing_entries
        )
    ]
    return tuple(duplicate)


@dataclass(frozen=True)
class FactoryDatabaseConnection:
    spreadsheet: gspread.Spreadsheet | None
    file_uploaded: bool
    connection_message: str

    def has_connection(self) -> bool:
        return self.spreadsheet is not None

    def read_database_entries(self) -> ReadingResponse:
        responses: dict[SheetType, SheetReadingResponse] = {
            SheetType.MATERIALS: _read_sheet_entries(SheetType.MATERIALS),
            SheetType.FACTORIES: _read_sheet_entries(SheetType.FACTORIES),
        }
        response = ReadingResponse.create(responses)
        return response

    def write_database_entries(
        self, entries_per_sheet: Mapping[SheetType, tuple[SheetEntry, ...]],
    ) -> WritingResponse:
        _LOGGER.info("Starting writing...")
        if self.spreadsheet is None:
            return WritingResponse(
                success=False,
                message=f"No spreadsheet connection available.",
            )
        spreadsheet: gspread.Spreadsheet = self.spreadsheet
        reading_response = self.read_database_entries()
        if not reading_response.success:
            return WritingResponse(
                success=False,
                message=f"Failed to read existing database entries: {reading_response.message}",
            )
        
        factory_database = reading_response.factory_database
        duplicate_entries = {
            sheet_type: _duplicate_entries(entries, factory_database.get_entries(sheet_type)) 
            for sheet_type, entries in entries_per_sheet.items()
        }

        if sum(len(duplicates) for duplicates in duplicate_entries.values()) > 0:
            def cancel_dialog() -> WritingResponse:
                return WritingResponse(success=False, message="Cancelled writing by user")


            entries_to_write = entries_per_sheet
            message = f"""Duplicate entries detected. Do you wish to write anyway?
{chr(10).join(
    f"{sheet.title}: {'\n'.join(str(duplicate) for duplicate in duplicates)} duplicate(s)"
    for sheet, duplicates in duplicate_entries.items() if duplicates
)}
"""
            response = confirm_action(
                on_confirm=lambda: _write_database_entries(spreadsheet, entries_per_sheet),
                on_cancel=lambda: cancel_dialog(),
                markdown_message=message,
            )
        else:
            entries_to_write = entries_per_sheet
            response = _write_database_entries(spreadsheet, entries_to_write)
        if response is None:
            return WritingResponse(success=False, message="", display=False)
        return response

    @classmethod
    def initialize_empty_factory_database_connection(cls) -> FactoryDatabaseConnection:
        return cls(
            spreadsheet=None,
            file_uploaded=False,
            connection_message="No connection established."
        )


def connect_to_factory_database(
    database: GTNHDatabase
) -> FactoryDatabaseConnection:
    uploaded_file = st.file_uploader(
        "Choose a json file to connect to your factory database (Google Sheets)",
        type="json"
    )
    if uploaded_file is None:
        return FactoryDatabaseConnection(spreadsheet=None, file_uploaded=False, connection_message="No file uploaded.")

    try:
        service_account_info = json.load(uploaded_file)
        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        client = gspread.authorize(credentials)
        _LOGGER.debug("✓ Authentication successful")
        spreadsheet = client.open_by_key(SHEET_ID)
        _LOGGER.debug("✓ Spreadsheet opened")

        connection = FactoryDatabaseConnection(
            spreadsheet=spreadsheet, file_uploaded=True, connection_message="Successfully connected to the factory database."
        )
        reading_response = connection.read_database_entries()
        if not reading_response.success:
            return FactoryDatabaseConnection(
                spreadsheet=None, file_uploaded=True, connection_message=f"Failed to read database entries: {reading_response.message}"
            )
        _LOGGER.debug("✓ Database entries read successfully")

        try:
            factories = reading_response.factory_database.get_factories(database)
        except KeyError as e:
            return FactoryDatabaseConnection(
                spreadsheet=None, file_uploaded=True, connection_message=f"Failed to read factories: {e}"
            )

        return FactoryDatabaseConnection(
            spreadsheet=spreadsheet, file_uploaded=True, 
            connection_message=f"Successfully connected to the factory database. Found {len(factories)} factories."
        )

    except Exception as e:
        _LOGGER.error("Exception type: %s", type(e).__name__)
        _LOGGER.error("Exception message: %s", e)
        _LOGGER.error(traceback.format_exc())
        return FactoryDatabaseConnection(
            spreadsheet=None, file_uploaded=True, connection_message=f"Failed to connect to the factory database: {e}"
        )
