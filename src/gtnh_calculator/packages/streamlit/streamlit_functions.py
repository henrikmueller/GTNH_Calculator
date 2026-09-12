import streamlit as st
import logging
from typing import Callable, TypeVar

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)

T = TypeVar("T")


@st.dialog("Confirm Action")
def confirm_action(
    on_confirm: Callable[[], T],
    on_cancel: Callable[[], T],
    markdown_message: str
) -> T | None:
    st.markdown(markdown_message)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancel", use_container_width=True):
            return on_cancel()

    with col2:
        if st.button("Confirm", type="primary", use_container_width=True):
            return on_confirm()
    return None
