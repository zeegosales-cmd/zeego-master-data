
import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
import time

st.set_page_config(page_title="Zeego Master Data Extractor", layout="wide")

st.title("Zeego.parts AI Master Data Extractor")
st.markdown("Upload a product catalogue PDF and generate the Master Bulk Upload file.")

# Sidebar for fixed parameters
st.sidebar.header("Batch Parameters")
type_part_number = st.sidebar.text_input("Type of Part Number", value="OEM")
equipment_type = st.sidebar.text_input("Equipment Type", value="Commercial Vehicles")
brand_name = st.sidebar.text_input("Brand Name", value="Sakura")
country = st.sidebar.text_input("Country", value="India")

st.header("1. Upload Files")
col1, col2 = st.columns(2)

with col1:
    uploaded_pdf = st.file_uploader("Upload Product Catalogue (PDF)", type="pdf")

with col2:
    start_page = st.number_input("Start Page Number (Actual PDF Page)", min_value=1, value=4)
    end_page = st.number_input("End Page Number (Actual PDF Page)", min_value=1, value=20)

st.header("2. AI Instruction & Samples")
st.markdown("Add custom samples below to train the AI on how to map categories.")

if 'samples' not in st.session_state:
    st.session_state.samples = []

with st.expander("Add Custom Mapping Sample"):
    sample_desc = st.text_input("Catalogue Text (e.g., 'Air Filter Primary')")
    sample_subcat = st.text_input("Target Sub Category (e.g., 'Air Filter')")
    sample_dev = st.text_input("Target Deviation (e.g., 'Primary Engine Air Filter')")
    if st.button("Add Sample (+)"):
        if sample_desc and sample_subcat and sample_dev:
            st.session_state.samples.append({
                "Description": sample_desc,
                "Sub Category": sample_subcat,
                "Deviation": sample_dev
            })
            st.success("Sample added!")

if st.session_state.samples:
    st.write("Current Samples:")
    st.dataframe(pd.DataFrame(st.session_state.samples))

# Logic Functions (Hardcoded backend matching to mimic AI)
def clean_description(desc):
    desc = re.sub(r'\.{2,}', '', desc)
    desc = re.sub(r'\s+', ' ', desc).strip()
    if "Primary" in desc and not desc.startswith("Primary"):
        desc = "Primary " + desc.replace("Primary", "").replace("  ", " ").strip()
    if "Secondary" in desc and not desc.startswith("Secondary"):
        desc = "Secondary " + desc.replace("Secondary", "").replace("  ", " ").strip()
    return desc.title()

def get_hsn_tax(desc_lower):
    if "air" in desc_lower: return "84213100", "18%"
    if "fuel" in desc_lower or "oil" in desc_lower: return "84212300", "18%"
    if "hydraulic" in desc_lower or "transmission" in desc_lower: return "84212900", "18%"
    return "8421", "18%" # Default for AI suggestion

def map_categories(desc, samples):
    desc_lower = desc.lower()
    veh_cat = "Goods Vehicles"
    cat = "Filters"
    
    # Check custom samples first
    for s in samples:
        if s['Description'].lower() in desc_lower:
            hsn, tax = get_hsn_tax(desc_lower)
            return veh_cat, cat, s['Sub Category'], s['Deviation'], "Blue Flag", hsn, tax
    
    # Default matching logic (simulating Categories Arrangement backend)
    status = "Green Flag"
    hsn, tax = get_hsn_tax(desc_lower)
    
    if "air filter" in desc_lower or "air element" in desc_lower:
        sub_cat = "Air Filter"
        if "cabin" in desc_lower: dev = "Cabin Air Filter"
        elif "primary" in desc_lower: dev = "Primary Engine Air Filter"
        elif "secondary" in desc_lower: dev = "Secondary Engine Air Filter"
        else: dev = "Round Air Filters"
    elif "fuel filter" in desc_lower or "water separator" in desc_lower:
        sub_cat = "Fuel Filter"
        if "separator" in desc_lower: dev = "Water Separator Filter"
        elif "primary" in desc_lower: dev = "Primary Fuel Filter"
        elif "secondary" in desc_lower: dev = "Secondary Fuel Filter"
        elif "element" in desc_lower: dev = "Fuel Filter Element"
        else: dev = "Primary Fuel Filter"
    elif "oil filter" in desc_lower or "oil element" in desc_lower:
        sub_cat = "Engine Oil Filter"
        if "bypass" in desc_lower: dev = "ByPass Oil Filter"
        elif "cartridge" in desc_lower or "element" in desc_lower: dev = "Oil Filter Cartridge"
        else: dev = "Main Oil Filters"
    elif "hydraulic" in desc_lower:
        sub_cat = "Hydraulic Filter"
        dev = "Hydraulic Filter"
    else:
        sub_cat = "AI Recommended"
        dev = "AI Recommended"
        status = "Yellow Flag" # AI not confident
        
    return veh_cat, cat, sub_cat, dev, status, hsn, tax

st.header("3. Generate Extraction")
if st.button("Run AI Master Data Extraction", type="primary"):
    if uploaded_pdf is not None:
        with st.spinner('Parsing PDF and applying Zeego Master Data rules...'):
            reader = PyPDF2.PdfReader(uploaded_pdf)
            main_part_regex = re.compile(r'^(\d*)([A-Z]{1,3}-[0-9]+(?:-[S])?)(.*)')
            all_parts = []
            
            # Ensure valid page range
            s_page = max(0, start_page - 1)
            e_page = min(len(reader.pages), end_page)
            
            for i in range(s_page, e_page):
                text = reader.pages[i].extract_text()
                if not text: continue
                
                page_parts = []
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if "uses " in line or "Note :" in line or "VOL :" in line or "CONT :" in line:
                        continue
                    match = main_part_regex.match(line)
                    if match:
                        part = match.group(2)
                        desc = match.group(3).strip()
                        if not re.search(r'^[A-Z0-9-]{4,}$', part): continue
                        page_parts.append({'Part Number': part, 'Description': desc})
                
                if len(page_parts) > 0:
                    rows = 5
                    cols = (len(page_parts) + rows - 1) // rows
                    if cols > 3: cols = 3
                    reordered = []
                    for r in range(rows):
                        for c in range(cols):
                            idx = c * rows + r
                            if idx < len(page_parts):
                                reordered.append(page_parts[idx])
                    all_parts.extend(reordered)
            
            final_data = []
            seen = set()
            for item in all_parts:
                pn = item['Part Number']
                if pn in seen: continue
                seen.add(pn)
                
                clean_name = clean_description(item['Description'])
                if len(clean_name) < 3: clean_name = "Filter Element"
                veh_cat, cat, sub_cat, dev, status, hsn, tax = map_categories(clean_name, st.session_state.samples)
                
                final_data.append({
                    'Part Number': pn,
                    'Description (Part Name)': clean_name,
                    'HSN Number': hsn,
                    'Tax Group': tax,
                    'Type of Part Number': type_part_number,
                    'Equipment type': equipment_type,
                    'Vehicle Category': veh_cat,
                    'Category': cat,
                    'Sub Category': sub_cat,
                    'Deviation': dev,
                    'B2B (%)': '',
                    'B2C (%)': '',
                    'Brand Name': brand_name,
                    'Country': country,
                    'Mapping Status': status
                })
            
            df_final = pd.DataFrame(final_data)
            
            # Save to Excel in memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Item Master')
            output.seek(0)
            
            st.success(f"Successfully extracted {len(df_final)} unique master items!")
            st.dataframe(df_final.head(10))
            
            st.download_button(
                label="⬇️ Download Zeego Master Format (Excel)",
                data=output,
                file_name="Zeego_Bulk_Upload.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.error("Please upload a PDF catalogue first.")

st.markdown("---")
st.markdown("*Zeego.parts Internal Master Data Portal - Powered by AI*")
