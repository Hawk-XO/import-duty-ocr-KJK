import re
import cv2
import numpy as np
from decimal import Decimal, ROUND_HALF_UP
from doctr.io import DocumentFile
from doctr.models import ocr_predictor


def draw_phantom_lines(image, y_rel_positions, color=(0, 0, 255), thickness=1):
    h, w = image.shape[:2]
    for y_rel in y_rel_positions:
        y_abs = int(y_rel * h)
        cv2.line(image, (0, y_abs), (w, y_abs), color, thickness)
    return image


def format_decimal(value_str):
    try:
        return Decimal(value_str.replace(",", "")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except:
        return Decimal("0.00")


def is_float(val):
    try:
        float(val.replace(",", ""))
        return True
    except:
        return False


def approx_equal(a, b, tol=0.1):
    return abs(a - b) <= tol


def extract_items_with_math_check(pdf_input):
    model = ocr_predictor(pretrained=True)

    # 📌 Accept file-like or string path
    if isinstance(pdf_input, str):
        doc = DocumentFile.from_pdf(pdf_input)
    else:
        pdf_input.seek(0)
        doc = DocumentFile.from_pdf(pdf_input.read())

    result = model(doc)
    pages = result.pages
    items = []

    for page_idx, page in enumerate(pages, start=1):
        lines = [" ".join(word.value for word in line.words) for block in page.blocks for line in block.lines]
        if not any("invoice" in line.lower() for line in lines):
            #print(f"⚠️ Skipping page {page_idx} — 'INVOICE' not found")   ----> debug code use it when running ocr debug
            continue

        # Convert PIL image to numpy for phantom drawing
        img = np.array(doc[page_idx - 1])
        y_lines = []

        for block in page.blocks:
            for line in block.lines:
                line_text = " ".join([word.value for word in line.words])
                if re.match(r'^\d+(\.\d{1,2})?[\s\.-]', line_text.strip()):
                    y = line.words[0].geometry[0][1]
                    y_lines.append(y)
                elif "total" in line_text.lower():
                    y_lines.append(line.words[0].geometry[0][1])

        debug_img = draw_phantom_lines(img.copy(), y_lines)
        # debug: cv2.imwrite("phantom_debug_page1.png", debug_img)

        y_sorted = sorted(y_lines)
        for i in range(len(y_sorted) - 1):
            y_start, y_end = y_sorted[i], y_sorted[i + 1]
            block_tokens = []

            for block in page.blocks:
                for line in block.lines:
                    for word in line.words:
                        y_mid = (word.geometry[0][1] + word.geometry[1][1]) / 2
                        if y_start < y_mid < y_end:
                            block_tokens.append(word.value)

            numeric_tokens = [t for t in block_tokens if is_float(t)]
            non_numeric_tokens = [t for t in block_tokens if not is_float(t)]

            if len(numeric_tokens) >= 3:
                qty = format_decimal(numeric_tokens[-3])
                unit_price = format_decimal(numeric_tokens[-2])
                amount = format_decimal(numeric_tokens[-1])

                if approx_equal(float(qty * unit_price), float(amount)):
                    items.append({
                        "Description": " ".join(non_numeric_tokens),
                        "Qty (from header index -1)": str(qty),
                        "Unit Price": str(unit_price),
                        "Amount": str(amount)
                    })

    return items, pages


def extract_mgt_metadata(pages):
    lines = []
    for page in pages:
        for block in page.blocks:
            for line in block.lines:
                line_text = " ".join(word.value for word in line.words).strip()
                lines.append(line_text)

    joined_text = "\n".join(lines)
    invoice_no_match = re.search(r'\bMGT-[A-Z0-9]+\b', joined_text)
    date_match = re.search(r'\b\d{2}-[A-Za-z]{3}-\d{2,4}\b', joined_text)

    return {
        'invoice_number': invoice_no_match.group(0) if invoice_no_match else '',
        'invoice_date': date_match.group(0) if date_match else ''
    }


def convert_mgt_to_xlnt_format(parsed_items):
    formatted = []
    for item in parsed_items:
        formatted.append([
            '',  # Artno
            item['Description'],
            '',  # Weight
            'pcs',  # Unit
            item['Qty (from header index -1)'],
            item['Unit Price']
        ])
    return formatted


# Optional test
if __name__ == "__main__":
    pdf_path = r"D:\MGT_E250513.pdf"
    items, pages = extract_items_with_math_check(pdf_path)
    for i, item in enumerate(items, 1):
        print(f"{i}. {item}")
