from __future__ import annotations
import streamlit as st
from io import BytesIO
import logging
from dataclasses import dataclass
import hashlib

from packages.utility.constants import ExampleFile
from packages.streamlit.session_state import SessionState

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class ConfigFile:
    file: BytesIO

    def file_hash(self) -> str:
        return hashlib.sha256(self.file.getvalue()).hexdigest()


def display_example_files(example_files: list[ExampleFile], session_state: SessionState) -> None:
    with st.expander('Example files'):
        cols = st.columns(len(example_files))

        for col, (i, example_file) in zip(cols, enumerate(example_files)):
            with col:
                st.markdown(f'### Example {i + 1}: {example_file.name}')

                st.markdown(example_file.description)
                if st.button('Calculate Crafting Chain', type='primary', key=f'example_{example_file.key}'):
                    session_state.example_file_key = example_file.key

                st.markdown(f'**Download config file for {example_file.name} example**:')
                with open(example_file.yaml_path, "rb") as file:
                    st.download_button(
                        label="Download yaml file",
                        data=file,
                        file_name=f"config_{example_file.key}_example.yaml"
                    )


def file_selection(example_files: list[ExampleFile], session_state: SessionState) -> ConfigFile | None:
    file_bytes = st.file_uploader("Choose a config file to specify the recipe chain", type='yaml')

    if file_bytes is None and session_state.example_file_key is not None:
        for example_file in example_files:
            if session_state.example_file_key == example_file.key:
                _LOGGER.info(f'Loading example file with key "{example_file.key}"')
                with open(example_file.yaml_path, "rb") as f:
                    file_bytes = BytesIO(f.read())
                break

    return ConfigFile(file_bytes) if file_bytes is not None else None
