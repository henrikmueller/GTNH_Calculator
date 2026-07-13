import streamlit as st
from io import BytesIO


def display_example_files():
    with st.expander('Example files'):
        a, b = st.columns(2)

        with a:
            st.markdown('### Example 1: High Octane Gasoline')

            st.markdown(f'''Uses _Oil Combs_ from Forestry and _Spruce Logs_ to produce _High Octane Gasoline_. 
        The config file specifies that the crafting chain should be optimized for maximal Gasoline output, while 
        adhering to the specified material constraints.
        ''')
            if st.button('Calculate Crafting Chain', type='primary', key='example_hog'):
                st.session_state['example_yaml'] = 'hog'
            # material_image(database.extracted_materials['f~gregtech~highoctanegasoline'])

            st.markdown('**Download config file for High Octane Gasoline example**:')
            with open("config/fixed_examples/config_hog_example.yaml", "rb") as file:
                st.download_button(
                    label="Download yaml file",
                    data=file,
                    file_name="config_hog_example.yaml"
                )

        with b:
            st.markdown('### Example 2: Platinum Line')
            
            st.markdown(f'''Extracts several elements from _Platinum Metallic Powder Dust_ via Sieving, Electrolysis, 
        Leaching, Pyrometallurgy, Solvent extraction and other processes: _Platinum_, _Rhodium_, _Ruthenium_, _Palladium_, 
        _Iridium_ and _Osmium_. The config file specifies that the crafting chain should be optimized for the unweighted 
        sum of all outputs, while adhering to the specified material constraints.
        ''')
            if st.button('Calculate Crafting Chain', type='primary', key='example_plat'):
                st.session_state['example_yaml'] = 'platinum'
            # material_image(database.extracted_materials['i~bartworks~gt.bwMetaGenerateddust~47'])

            st.markdown('**Download config file for Platinum Line example**:')
            with open("config/fixed_examples/config_plat_line_example.yaml", "rb") as file:
                st.download_button(
                    label="Download yaml file",
                    data=file,
                    file_name="config_plat_line_example.yaml"
                )


def file_selection() -> BytesIO | None:
    uploaded_file = st.file_uploader("Choose a config file to specify the recipe chain", type='yaml')

    if uploaded_file is None and 'example_yaml' in st.session_state:
        match st.session_state['example_yaml']:
            case 'hog':
                with open("config/fixed_examples/config_hog_example.yaml", "rb") as f:
                    uploaded_file = BytesIO(f.read())
            case 'platinum':
                with open("config/fixed_examples/config_plat_line_example.yaml", "rb") as f:
                    uploaded_file = BytesIO(f.read())
                    
    return uploaded_file
