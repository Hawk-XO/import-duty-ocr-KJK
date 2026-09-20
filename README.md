# import-duty-ocr

A Flask web app that reads import invoices (PDF), extracts the line items with OCR, and calculates the landed cost and import duty for each item. Records are stored in MySQL and can be searched, edited, recalculated and exported.

> **Note:** This is the original prototype and proof of concept. It was later rebuilt into a more complete version for internal company use, so some rough edges remain here (see [Known issues](#known-issues)).

## Features

- Upload an invoice PDF and extract line items and metadata with [docTR](https://github.com/mindee/doctr). There are three separate parsers, one per invoice layout:
  - `ocr_utils.py` finds items by grouping lines under an article-number header and pulls metadata by regex
  - `extramet_ocr.py` finds items by row position and regex, and handles multi-line descriptions
  - `mgt_ocr.py` accepts a row only if `qty × unit price ≈ amount`
- Review and correct the extracted values in a form before saving, or enter an invoice manually.
- Per-item duty calculation (formulas below).
- Search by invoice number, with a full or summary view.
- Edit an invoice and recalculate every derived value.
- Export to XLSX, and download an A3 landscape PDF of the current view (full working or summary), generated with WeasyPrint.

## How duty is calculated

Default rates are BCD 10%, SWS 10% and IGST 18%, all editable per item.

| Value | Formula |
|---|---|
| Material cost | quantity × rate |
| GRN cost (INR) | material cost × currency exchange rate |
| Freight (item) | total freight × freight exchange rate, split by the item's share of GRN cost |
| Insurance (item) | total GRN cost × insurance %, split by the item's share of GRN cost |
| Assessable value | GRN cost + freight + insurance + misc |
| BCD (basic customs duty) | assessable value × duty % |
| SWS (social welfare surcharge) | BCD × SWS % |
| IGST | (assessable value + BCD + SWS) × IGST % |
| Inward cost with duty | GRN cost + BCD + SWS |

## Tech stack

Python · Flask · MySQL · docTR (PyTorch) · OpenCV · pandas / openpyxl · WeasyPrint · Bootstrap 5

## Running it

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Create a MySQL database `inventory_db` with a table `inventory_table_samplee` (one row per invoice line item, with the invoice-level fields repeated on each row).

3. Set the credentials as environment variables:

   ```
   DB_PASSWORD=your_mysql_password
   SECRET_KEY=any-random-string
   ```

4. Put the HTML files in a `templates/` folder, then run:

   ```bash
   python app.py
   ```

   Open http://127.0.0.1:5000. The first OCR run is slow while docTR downloads its models.

   PDF export uses WeasyPrint, which needs some system libraries (Pango on Linux/macOS, GTK on Windows). See the [WeasyPrint install guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) if the PDF button fails.

## Known issues

- Written as a prototype: DB host and user are hardcoded to `localhost` / `root`, there is no authentication, and no tests.
- Some paths in the OCR scripts are Windows-specific (`D:\...`) and only matter for their standalone test blocks.
- The "+ Add Item" button on the edit page is not wired up.
- Misc charges are added in full to every line item's assessable value instead of being split proportionally.
- The parsers were tuned to specific invoice layouts, so a new layout needs a new parser.
