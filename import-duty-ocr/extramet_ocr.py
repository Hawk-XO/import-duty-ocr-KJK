import os
import cv2
import numpy as np
import re
from datetime import datetime
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

PDF_PATH = r"D:\Invoice No 4934.pdf"
OUTPUT_DIR = r"D:\inventory_ocr combined\inventory_ocr_combined"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def extract_items(page, image_np, page_num, output_dir=None):
    image_h, image_w = image_np.shape[:2]
    all_words = []
    lines = {}

    for block in page.blocks:
        for line in block.lines:
            for word in line.words:
                x = int(word.geometry[0][0] * image_w)
                y = int(word.geometry[0][1] * image_h)
                text = word.value.strip().replace(",", "")
                all_words.append({"x": x, "y": y, "text": text})

    # group into lines
    for w in sorted(all_words, key=lambda w: (w["y"], w["x"])):
        y = w["y"]
        matched = False
        for key in lines:
            if abs(key - y) < 12:
                lines[key].append(w)
                matched = True
                break
        if not matched:
            lines[y] = [w]

    sorted_y = sorted(lines.keys())
    footer_keywords = ["extramet ag", "office@extramet.ch", "+41", "www.extramet.ch", "net pur"]
    items = []
    skip_lines = set()
    header_found = False

    i = 0
    while i < len(sorted_y):
        y = sorted_y[i]
        tokens = sorted(lines[y], key=lambda t: t["x"])
        line_texts = [t["text"] for t in tokens]
        line_str = " ".join(line_texts).lower()

        # Stop at footer or summary section
        if any(k in line_str for k in footer_keywords):
            break

        # Find header once
        if not header_found and any("lne" in t.lower() for t in line_texts):
            header_found = True
            i += 1
            continue
        if not header_found:
            i += 1
            continue

        match = re.match(
            r"(\d{1,2}\.\d{2})\s+(\S+)\s+(\d+)\s+(\S+)?\s+(\d+\.\d{2})\s+(\d+\.\d{2})\s+(.*)",
            " ".join(line_texts)
        )

        if match:
            lne, artnr, qty, unit, price, total, desc_part = match.groups()
            try:
                lne_val = float(lne.replace(",", ".").replace("\xa0", "").strip())
                if not (1 <= lne_val <= 100):
                    i += 1
                    continue
                lne = f"{lne_val:.2f}"
            except ValueError:
                i += 1
                continue

            # Clean and continue multiline description
            desc_lines = [desc_part.strip()]
            j = i + 1

            while j < len(sorted_y):
                next_tokens = [w["text"] for w in sorted(lines[sorted_y[j]], key=lambda t: t["x"])]
                next_line_str = " ".join(next_tokens).lower()
                if re.match(r"\d{1,2}\.\d{2}", next_tokens[0]) or any(k in next_line_str for k in footer_keywords):
                    break
                desc_lines.append(" ".join(next_tokens).strip())
                skip_lines.add(sorted_y[j])
                j += 1

            # Join and clean description
            description = " ".join(desc_lines).strip()
            if description.lower().startswith("eur "):
                description = description[4:].strip()

            item = {
                "lne": lne,
                "artnr": artnr,
                "qty": qty,
                "unit": unit or "",
                "price": price,
                "total": total,
                "description": description
            }
            items.append(item)
            print(f"✅ MATCH @Y={y} → Lne: {lne}, ArtNr: {artnr}")
            i = j

        else:
            i += 1

    # Optional: draw skipped phantom lines
    if output_dir:
        for y in sorted_y:
            if y in skip_lines:
                cv2.line(image_np, (0, y), (image_w, y), (0, 0, 255), 1)
        out_path = os.path.join(output_dir, f"page_{page_num + 1}_phantom.png")
        cv2.imwrite(out_path, image_np)

    return items

def deduplicate_items_by_lne_artnr(items):
    unique = {}
    for item in items:
        key = (item["lne"], item["artnr"])
        if key not in unique or len(item["description"]) > len(unique[key]["description"]):
            unique[key] = item
    return list(unique.values())

def extract_invoice_metadata(pages):
    invoice_number = None
    invoice_date = None
    for page in pages:
        for block in page.blocks:
            for line in block.lines:
                line_text = " ".join([word.value for word in line.words]).strip()
                line_text_lower = line_text.lower()
                if any(k in line_text_lower for k in ["invoice no", "invoice number", "rechnung nr", "number:"]):
                    match = re.search(r"\b\d{4,6}\b", line_text)
                    if match:
                        invoice_number = match.group()
                if any(k in line_text_lower for k in ["date", "datum"]):
                    match = re.search(r"\b\d{2}[-./]\d{2}[-./]\d{4}\b", line_text)
                    if match:
                        raw_date = match.group()
                        try:
                            parsed = datetime.strptime(raw_date, "%d-%m-%Y")
                            invoice_date = parsed.strftime("%Y-%m-%d")
                        except:
                            invoice_date = raw_date
    return invoice_number, invoice_date

def extract_extramet_data(pdf_input, output_dir=None):
    model = ocr_predictor(pretrained=True)
    doc_images = DocumentFile.from_pdf(pdf_input)
    ocr_result = model(doc_images)

    all_items = []
    for i, (img, page) in enumerate(zip(doc_images, ocr_result.pages)):
        img_np = np.array(img)
        page_items = extract_items(page, img_np, i, output_dir)
        all_items.extend(page_items)

    invoice_number, invoice_date = extract_invoice_metadata(ocr_result.pages)
    all_items = deduplicate_items_by_lne_artnr(all_items)

    print("\n📦 [FINAL STRUCTURED ITEMS]")
    for idx, item in enumerate(all_items, 1):
        print(f"\n📍 ITEM {idx}")
        print("-" * 35)
        for key in ['lne', 'artnr', 'qty', 'unit', 'price', 'total', 'description']:
            print(f"{key.capitalize():<12}: {item[key]}")

    print("\n📑 [FINAL METADATA]")
    print(f"Invoice Number : {invoice_number or '❌ Not Found'}")
    print(f"Invoice Date   : {invoice_date or '❌ Not Found'}")

    return all_items, invoice_number, invoice_date

if __name__ == "__main__":
    extract_extramet_data(PDF_PATH, OUTPUT_DIR)
