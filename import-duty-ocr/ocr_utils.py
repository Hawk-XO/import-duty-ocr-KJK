from pdf2image import convert_from_path
from doctr.models import ocr_predictor
import os
import numpy as np
import re
from doctr.io import DocumentFile
pdf_path=r"D:\Invoice_1311671.pdf"
model = ocr_predictor(pretrained=True)

def extract_text_blocks(pdf_path):
    return model(DocumentFile.from_pdf(pdf_path)).export()['pages']

def extract_fields_from_text(text_blocks):
    lines = []

    for block in text_blocks:
        if 'blocks' not in block:
            continue
        for inner_block in block['blocks']:
            if 'lines' not in inner_block:
                continue
            for line in inner_block['lines']:
                line_text = " ".join(word['value'] for word in line['words'])
                lines.append(line_text)

    joined_text = "\n".join(lines)

    extracted = {
        "company_name": "XLNT" if any("XLNT" in line for line in lines) else None,
        "invoice_number": None,
        "invoice_date": None,
        "delivery_date": None,
        "packing_list": None,
        "order_number": None,
        "customer_id": None,
        "customer_name": None,
    }

    patterns = {
        "invoice_number": r'Commercial invoice no[:\s\.]*([0-9]+)',
        "invoice_date": r'Invoice date[:\s\.]*([0-9]{2}\.[0-9]{2}\.[0-9]{4})',
        "delivery_date": r'Delivery date[:\s\.]*([0-9]{2}\.[0-9]{2}\.[0-9]{4})',
        "packing_list": r'packing list[:\s\.]*([0-9]+)',
        "order_number": r'Order number[:\s\.]*([0-9]+)',
        "customer_id": r'Customer\s*(?:ID|I D)[:\s\.]*([0-9]+)',
        "customer_name": r'Contact[:\s\.]*([A-Za-z]+)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, joined_text, re.IGNORECASE)
        if match:
            extracted[key] = match.group(1)

    return extracted


def extract_table_items(text_blocks):
    lines = []

    # Step 1: Extract all lines from OCR result
    for block in text_blocks:
        if 'blocks' not in block:
            continue
        for inner in block['blocks']:
            if 'lines' not in inner:
                continue
            for line in inner['lines']:
                text = " ".join(w['value'] for w in line['words']).strip()
                lines.append(text)

    # Step 2: More flexible header detection using start marker
    start_index = None
    for i, line in enumerate(lines):
        if re.search(r'Art\.?Nr', line, re.IGNORECASE):
            start_index = i
            break

    if start_index is None:
        print("❌ Couldn't find Art.Nr header — check OCR output structure.")
        return []

    # Step 3: Slice from detected start to end
    data_lines = lines[start_index + 1:]
    stop_keywords = ['subtotal', 'total', 'balance owing', 'paid']
    filtered = []
    for line in data_lines:
        if any(kw in line.lower() for kw in stop_keywords):
            break
        filtered.append(line)

    # Step 4: Group between one Art.Nr and the next
    blocks = []
    current = []
    for line in filtered:
        tokens = line.split()
        if not tokens:
            continue
        if re.match(r'^\d{7,}(\.[A-Za-z0-9])?$', tokens[0]):
            if current:
                blocks.append(current)
                current = []
        current.append(line)
    if current:
        blocks.append(current)

    # Step 5: Parse each block
    items = []
    for block in blocks:
        words = []
        for line in block:
            words.extend(line.strip().split())

        if not words or not re.match(r'^\d{7,}(\.[A-Za-z0-9])?$', words[0]):
            continue

        artnr = words[0]
        rest = words[1:]

        float_vals = [w for w in rest if re.match(r'\d+\.\d+', w)]
        units = [w for w in rest if w.lower() in ['grs', 'gms', 'kg', 'g','pcs.','pcs','Nos','No','set','Ea','kgs']]

        weight_val = qty = price = weight_unit = ""

        if len(float_vals) >= 3:
            weight_val, qty, price = float_vals[-3:]
        elif len(float_vals) == 2:
            qty, price = float_vals[-2:]
        elif len(float_vals) == 1:
            price = float_vals[0]

        if units:
            weight_unit = units[-1]

        # Rebuild description       
        desc_tokens = [w for w in rest if w not in float_vals and w != weight_unit]
        description = " ".join(desc_tokens).strip(" ,.-")

        items.append([artnr, description, weight_val, weight_unit, qty, price])

    return items


# === TESTING ===
if __name__ == '__main__':
    text_blocks = extract_text_blocks(pdf_path)

    metadata = extract_fields_from_text(text_blocks)
    line_items = extract_table_items(text_blocks)

    print("\n=== METADATA ===")
    for key, val in metadata.items():
        print(f"{key}: {val}")

    print("\n=== TABLE ITEMS ===")
    for item in line_items:
        print(item)
