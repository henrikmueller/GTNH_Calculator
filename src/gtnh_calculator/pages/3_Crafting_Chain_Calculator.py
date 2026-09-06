import streamlit as st
import logging
import sys

from packages.streamlit.crafting_chain_display import CraftingChainCalculationDisplay
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.streamlit.streamlit_functions import (
    load_database, load_crafting_chain_database, show_memory_usage
)
from packages.streamlit.streamlit_logic import (
    display_example_files, file_selection, ConfigFile
)
from packages.streamlit.session_state import SessionState
from packages.utility.constants import EXAMPLE_FILES

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


SESSION_STATE_KEY = 'crafting_chain_calculator'

_LOGGER.warning('\n\nSTARTING NEW PAGE')

st.set_page_config(
    page_title="GTNH: Crafting Chain Calculator",
    page_icon="🏭",
    layout="wide"
)
st.markdown('# GTNH Calculator')
st.markdown('## CraftingChainConfig File')

database: GTNHDatabase = load_database()
session_state = SessionState.get(SESSION_STATE_KEY)
show_memory_usage(database)

display_example_files(EXAMPLE_FILES, session_state)
uploaded_file: ConfigFile | None = file_selection(EXAMPLE_FILES, session_state)

if uploaded_file is not None:
    with st.spinner('Reducing database...', show_time=True):
        _LOGGER.info(f'Uploaded file hash: {uploaded_file.file_hash()}')
        _LOGGER.info(f'Stored file hash: {session_state.file_hash}')

        if not session_state.has_active_file() or session_state.file_hash != uploaded_file.file_hash():
            session_state.wipe()
        session_state.file_hash = uploaded_file.file_hash()
        crafting_chain_database = load_crafting_chain_database(uploaded_file, database, session_state)
else:
    crafting_chain_database = None


config = crafting_chain_database.config if crafting_chain_database is not None else None
if crafting_chain_database is not None and config is not None:
    all_materials = crafting_chain_database.materials(database)
    crafting_chain_calculation_display = CraftingChainCalculationDisplay(
        database=database,
        crafting_chain_database=crafting_chain_database,
        config=config,
        all_materials=all_materials,
        session_state=session_state
    )
    crafting_chain_calculation_display.display_page()
