# app.py
from flask import Flask, render_template, request, redirect ,session, url_for, flash # Your existing OCR function
import mysql.connector
from datetime import datetime
from ocr_utils import extract_fields_from_text,extract_table_items,extract_text_blocks
from flask import jsonify 
import json
from werkzeug.utils import secure_filename
import tempfile
from doctr.models import ocr_predictor
from doctr.io import DocumentFile
import os
from flask import send_file
import pandas as pd
from io import BytesIO
from openpyxl.utils import get_column_letter
from openpyxl import load_workbook
from recalculation_utils import recalculate_invoice 
from decimal import Decimal 
from mgt_ocr import extract_items_with_math_check,convert_mgt_to_xlnt_format,extract_mgt_metadata  # if you're using this for date parsing 
from extramet_ocr import extract_extramet_data




def insert_new_item_row(item, rate_in_inr, material_cost):
    cursor.execute("""
        INSERT INTO inventory_table_samplee (
            Artno, Specification, Type_of_Product, Quantity, qty_type, Rate_in_Euro,
            Rate_in_Inr, Material_Cost, Invoice_no, Duty_percentage_item,
            SW_srchrg_percent, IGST_percentage, GWO
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        item['Artno'], item['Specification'], item['Type_of_Product'],
        item['Quantity'],item['qty_type'], item['Rate_in_Euro'], rate_in_inr,   
        material_cost, item['Invoice_no'], item['Duty_percentage_item'],
        item['SW_srchrg_percent'], item['IGST_percentage'], item['GWO']
    ))
    conn.commit()



def update_common_data(invoice_no, data):
    # Apply changes only to rows with that invoice number (we'll update all rows for consistency)
    fields = ', '.join(f"{key}=%s" for key in data)
    values = list(data.values())
    cursor.execute(f"""
        UPDATE inventory_table_samplee SET {fields} 
        WHERE Invoice_no = %s
    """, values + [invoice_no])
    conn.commit()


def update_item_rows(invoice_no, items):
    for item in items:
        cursor.execute("""
            UPDATE inventory_table_samplee
            SET Quantity = %s, IGST_percentage = %s
            WHERE S_no = %s AND Invoice_no = %s
        """, (item['Quantity'], item['IGST_percentage'], item['S_no'], invoice_no))
    conn.commit()


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
model = ocr_predictor(pretrained=True)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only")


# Connect to MySQL
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password=os.environ["DB_PASSWORD"],
    database="inventory_db"
)
cursor = conn.cursor()
def get_common_data(invoice_no):
    cursor.execute("SELECT * FROM inventory_table_samplee WHERE Invoice_no = %s LIMIT 1", (invoice_no,))
    row = cursor.fetchone()
    if not row:
        return None
    column_names = [desc[0] for desc in cursor.description]
    return dict(zip(column_names, row))

def get_item_rows(invoice_no):
    cursor.execute("SELECT * FROM inventory_table_samplee WHERE Invoice_no = %s", (invoice_no,))
    rows = cursor.fetchall()
    cols = [desc[0] for desc in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


def convert_date(date_str):
    """
    Converts date from 'dd.mm.yyyy' (OCR format) to 'yyyy-mm-dd' (HTML date input format).
    """
    try:                        
        return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception as e:
        print("Date conversion error:", e)
        return ""
     # assuming you have a util to convert date formats


from flask import request, redirect, url_for, session, render_template
from werkzeug.utils import secure_filename
import os
import tempfile

# Import your XLNT and MGT OCR modules


@app.route('/upload', methods=['GET', 'POST'])
def upload_invoice():
    if request.method == 'POST':
        if 'pdf_file' not in request.files or 'company_selected' not in request.form:
            return "Missing file or company selection", 400

        file = request.files['pdf_file']
        company = request.form.get('company_selected')

        if file.filename == '':
            return "No selected file", 400

        if file and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(file.filename)
            temp_path = os.path.join(tempfile.gettempdir(), filename)
            file.save(temp_path)

            # ================= XLNT PIPELINE =================
            if company == 'XLNT':
                text_blocks = extract_text_blocks(temp_path)
                meta = extract_fields_from_text(text_blocks)
                item_data = extract_table_items(text_blocks)

                metadata = {
                    'Invoice_no': meta.get('invoice_number', ''),
                    'Invoice_date': convert_date(meta.get('invoice_date', '')),
                    'PARTY_NAME': company,
                    'GRN_no': '',
                    'Material_Recieved_Date': '',
                    'Invoice_currency': 'EUR',
                    'Currency_Exchange_Rate': '',
                    'BOE_no': '',
                    'BOE_date': '',
                    'AWB_no': '',
                    'AWB_date': '',
                    'BOE_frieght_charges': '',
                    'BOE_insurance_charges': '',
                    'BOE_insurance_percentage': '',
                    'BOE_Misc': '',
                    'Grade': '',
                }

                items = []
                for row in item_data:
                    items.append({
                        'Artno': row[0],
                        'Specification': row[1],
                        'Quantity': row[2],
                        'Unit': row[3],
                        'Rate_in_Euro': row[4],
                        'Final_Amount': row[5],
                        'Duty_percentage_item': 10,
                        'SW_srchrg_percent': 10,
                        'IGST_percentage': 18,
                        'GWO': ''
                    })

            # ================= MGT PIPELINE =================
            elif company == 'MGT':
                parsed_items, text_blocks = extract_items_with_math_check(temp_path)
                item_data = convert_mgt_to_xlnt_format(parsed_items)
                mgt_meta = extract_mgt_metadata(text_blocks)

                metadata = {
                    'Invoice_no': mgt_meta.get('invoice_number', ''),
                    'Invoice_date': mgt_meta.get('invoice_date', ''),
                    'PARTY_NAME': company,
                    'GRN_no': '',
                    'Material_Recieved_Date': '',
                    'Invoice_currency': 'EUR',
                    'Currency_Exchange_Rate': '',
                    'BOE_no': '',
                    'BOE_date': '',
                    'AWB_no': '',
                    'AWB_date': '',
                    'BOE_frieght_charges': '',
                    'BOE_insurance_charges': '',
                    'BOE_insurance_percentage': '',
                    'BOE_Misc': '',
                    'Grade': '',
                }

                items = []
                for row in item_data:
                    items.append({
                        'Artno': row[0],
                        'Specification': row[1],
                        'Quantity': row[4],
                        'Unit': row[3],
                        'Rate_in_Euro': row[5],
                        'Final_Amount': '',
                        'Duty_percentage_item': 10,
                        'SW_srchrg_percent': 10,
                        'IGST_percentage': 18,
                        'GWO': ''
                    })

            # ================= EXTRAMET PIPELINE =================
            elif company == 'EXTRAMET':
                parsed_items, invoice_number, invoice_date = extract_extramet_data(temp_path)

                metadata = {
                    'Invoice_no': invoice_number or '',
                    'Invoice_date': invoice_date or '',
                    'PARTY_NAME': company,
                    'GRN_no': '',
                    'Material_Recieved_Date': '',
                    'Invoice_currency': 'EUR',
                    'Currency_Exchange_Rate': '',
                    'BOE_no': '',
                    'BOE_date': '',
                    'AWB_no': '',
                    'AWB_date': '',
                    'BOE_frieght_charges': '',
                    'BOE_insurance_charges': '',
                    'BOE_insurance_percentage': '',
                    'BOE_Misc': '', 
                    'Grade': '',
                }

                items = []
                for row in parsed_items:
                    items.append({
                        'Artno': row['artnr'],
                        'Specification': row['description'],
                        'Quantity': row['qty'],
                        'Unit': row['unit'],
                        'Rate_in_Euro': row['price'],
                        'Final_Amount': row['total'],
                        'Duty_percentage_item': 10,
                        'SW_srchrg_percent': 10,
                        'IGST_percentage': 18,
                        'GWO': ''
                    })

            else:
                return "Unsupported company type", 400

            session['metadata'] = metadata
            session['item_rows'] = items
            return redirect(url_for('index'))

    return render_template('upload.html')



@app.route('/')
def home():
    return redirect(url_for('start'))
@app.route('/manual', methods=['GET', 'POST'])
def manual_input():
    session.pop('metadata', None)
    session.pop('item_rows', None)
    session['manual_input'] = True  # Flag to indicate manual entry
    return redirect(url_for('index'))




@app.route('/input', methods=['GET', 'POST'])
def index():
    metadata = session.get('metadata', {})  # Get from session or empty dict
    item_rows = session.get('item_rows', [])
    if session.pop('manual_input', False):  # Remove flag after reading
        item_rows = [{}]  # One empty item row

    if request.method == 'POST':
        invoice_no = request.form['Invoice_no']
        invoice_date = request.form['Invoice_date']
        party_name = request.form['PARTY_NAME']
        grn_no = request.form['GRN_no']
        material_received_date = request.form['Material_Recieved_Date']
        invoice_currency = request.form['Invoice_currency_custom'] if request.form.get('Invoice_currency_select') == 'Custom' else request.form['Invoice_currency_select']
        currency_exchange_rate = float(request.form['Currency_Exchange_Rate'])
        boe_no = request.form['BOE_no']
        boe_date = request.form['BOE_date']
        awb_no = request.form['AWB_no']
        awb_date = request.form['AWB_date']

        # NEW FIELDS
        freight_charges = float(request.form.get('Freight_Charges', 0))
        freight_ex_rate = float(request.form.get('Freight_Exchange_Rate', 0))
        total_freight = freight_charges * freight_ex_rate

        boe_insurance_percentage = float(request.form['BOE_insurance_percentage'])
        grade = request.form['Grade']
        meis_license = request.form['MEIS_License'] if request.form.get('meis_license_use') == 'Yes' else ''
        boe_misc = float(request.form.get('BOE_Misc', 0))

        total_items = len(request.form.getlist("Artno"))

        # Item-wise fields
        artnos = request.form.getlist('Artno')
        specs = request.form.getlist('Specification')
        type_raw = request.form.getlist('Type_of_Product')
        type_custom = request.form.getlist('Type_of_Product_custom')
        types = [type_custom[i] if type_raw[i] == 'Custom' else type_raw[i] for i in range(len(type_raw))]
        qty_type = request.form.getlist("Qty_type")
        qtys = list(map(float, request.form.getlist('Quantity')))
        rates = list(map(float, request.form.getlist('Rate_in_Euro')))

        def padded_list(name):
            lst = request.form.getlist(name)
            return lst + ['0'] * (total_items - len(lst))  # pad with zeros if missing

        igst_pcts = [float(x or 0) for x in padded_list("IGST_percentage")]
        duties = [float(x or 0) for x in padded_list("Duty_percentage_item")]
        sw_pcts = [float(x or 0) for x in padded_list("SW_srchrg_percent")]
        gwos = request.form.getlist('GWO')
        if len(gwos) < len(artnos):
            gwos += [""] * (len(artnos) - len(gwos))

        matcost_euro_list = [(qtys[i] * rates[i]) for i in range(len(qtys))]
        matcost_grn_list = [(matcost_euro_list[i] * currency_exchange_rate) for i in range(len(qtys))]
        total_matcost_grn = sum(matcost_grn_list)

        for i in range(len(artnos)):
            material_cost = round(qtys[i] * rates[i], 2)
            rate_in_inr = round(rates[i] * currency_exchange_rate, 2)
            material_cost_grn = round(material_cost * currency_exchange_rate, 2)

            freight = round((material_cost_grn / total_matcost_grn) * total_freight, 2) if total_matcost_grn else 0
            boe_insurance = round((total_matcost_grn * boe_insurance_percentage / 100), 2)
            insurance = round((material_cost_grn / total_matcost_grn) * boe_insurance, 2) if total_matcost_grn else 0
            gwo = gwos[i] if i < len(gwos) and gwos[i] else ""

            total_ass_val = round(material_cost_grn + freight + insurance + boe_misc, 2)
            customs_duty = round(total_ass_val * (duties[i] / 100), 2)
            sw_srchrg_value = round(customs_duty * (sw_pcts[i] / 100), 2)
            total_duty = round(customs_duty + sw_srchrg_value, 2)
            total_ass_n_cd = round(total_ass_val + total_duty, 2)
            igst_value = round(total_ass_n_cd * (igst_pcts[i] / 100), 2)
            Inward_Total_Value_w_IGST = round(material_cost_grn + total_duty, 2)
            inward_total_duty_n_igst = round(total_duty + igst_value, 2)
            percent_of_cd = round((total_duty / material_cost_grn) * 100, 2) if material_cost_grn else 0
            import_duty_igst_percent = round((inward_total_duty_n_igst / material_cost_grn) * 100, 2) if material_cost_grn else 0

            cursor.execute("""
                INSERT INTO inventory_table_samplee (
                    Artno, PARTY_NAME, Specification, Type_of_Product,
                    Quantity, qty_type, Rate_in_Euro, Currency_Exchange_Rate, Rate_in_Inr,
                    Material_Cost, Materialcost_GRN, Freight, Insurance, BOE_Misc,
                    Total_Ass_Value, Duty_percentage_item, Customs_Duty,
                    SW_srchrg_percent, SW_srchrg_Value, Total_Duty, Total_Ass_n_CD,
                    IGST_percentage, IGST_Value, Inward_Total_Value_w_IGST,
                    Inward_total_duty_n_IGST, percent_of_CD, Import_Duty_n_IGST_percent,
                    Invoice_no, Invoice_date, GRN_no, Material_Recieved_Date,
                    Invoice_currency, BOE_no, BOE_date, AWB_no, AWB_date,
                    BOE_frieght_charges, BOE_insurance_charges, BOE_insurance_percentage,
                    MEIS_License, GWO, Grade,
                    Freight_Charges, Freight_Exchange_Rate
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s)
            """, (
                artnos[i], party_name, specs[i], types[i],
                qtys[i], qty_type[i], rates[i], currency_exchange_rate, rate_in_inr,
                material_cost, material_cost_grn, freight, insurance, boe_misc,
                total_ass_val, duties[i], customs_duty,
                sw_pcts[i], sw_srchrg_value, total_duty, total_ass_n_cd,
                igst_pcts[i], igst_value, Inward_Total_Value_w_IGST,
                inward_total_duty_n_igst, percent_of_cd, import_duty_igst_percent,
                invoice_no, invoice_date, grn_no, material_received_date,
                invoice_currency, boe_no, boe_date, awb_no, awb_date,
                total_freight, boe_insurance, boe_insurance_percentage,
                meis_license, gwo, grade,
                freight_charges, freight_ex_rate
            ))

        conn.commit()
        return redirect('/search')

    return render_template('input.html', metadata=metadata, item_rows=item_rows)


@app.route('/delete_invoice', methods=['POST'])
def delete_invoice():
    invoice_no = request.form.get('invoice_no')
    if not invoice_no:
        return "Invoice number missing", 400

    try:
        connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.environ["DB_PASSWORD"],
        database="inventory_db"
    )
        with connection.cursor() as cursor:
            # Delete the invoice entries
            cursor.execute("DELETE FROM inventory_table_samplee WHERE Invoice_no = %s", (invoice_no,))
        connection.commit()
        connection.close()
        flash(f"Invoice {invoice_no} has been deleted successfully.", "success")
        return redirect(url_for('search'))
    except Exception as e:
        return f"Error deleting invoice: {str(e)}", 500

@app.route('/search', methods=['GET', 'POST'])
def search():
    from io import BytesIO

    # Step 1: Determine invoice_no and view_mode
    if request.method == "POST":
        invoice_no = request.form.get("invoice_no", "").strip()
        view_mode = request.form.get("view_mode", "full")
    else:
        invoice_no = request.args.get("invoice_no", "").strip() 
        view_mode = request.args.get("view_mode", "full")

    if not invoice_no:
        return render_template('search.html', item_rows=None, item_columns=None, common_data=None,
                               totals=None, searched=None, view_mode=view_mode)

    # Step 2: Fetch data from DB
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.environ["DB_PASSWORD"],
        database="inventory_db"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory_table_samplee WHERE Invoice_no = %s", (invoice_no,))
    records = cursor.fetchall()
    columns = [i[0] for i in cursor.description]
    conn.close()

    if not records:
        return render_template('search.html', item_rows=[], item_columns=[], common_data={},
                               searched=invoice_no, totals={}, view_mode=view_mode)

    all_rows = [dict(zip(columns, row)) for row in records]

    # Step 3: Column logic
    common_columns = [
        'Invoice_no', 'Invoice_date', 'GRN_no', 'Material_Recieved_Date',
        'Invoice_currency', 'BOE_no', 'BOE_date', 'AWB_no', 'AWB_date',
        'BOE_frieght_charges', 'BOE_insurance_charges', 'BOE_insurance_percentage',
        'PARTY_NAME', 'MEIS_License', 'Grade',
        'Freight_Charges', 'Freight_Exchange_Rate'  # Add these too
    ]


    if view_mode == 'summary':
        item_columns = [
            'GWO', 'Artno', 'Specification', 'Type_of_Product',
            'Quantity', 'Qty_type', 'Currency_Exchange_Rate', 'Materialcost_GRN',
            'Customs_Duty', 'SW_srchrg_Value', 'Total_Duty',
            'Inward_Total_Value_w_IGST', 'IGST_Value'
        ]
    else:
        excluded_fields = set(common_columns + ['S_no'])
        item_columns = ['GWO'] + [col for col in columns if col not in excluded_fields and col != 'GWO']


    # Step 5: Build data
    common_data = {col: all_rows[0].get(col, '') for col in common_columns}
    item_rows = [{col: row.get(col, '') for col in item_columns} for row in all_rows]

    if view_mode == 'summary':
        for i, row in enumerate(item_rows):
            row['S.no'] = i + 1

    # Step 6: Totals
    exclude_totals = {'S.no', 'S_no', 'Artno', 'Specification', 'Type_of_Product', 'Currency_Exchange_Rate', 'GWO'}
    totals = {}
    for col in item_columns:
        if col in exclude_totals:
            totals[col] = ''
        else:
            try:
                totals[col] = round(sum(float(row[col]) for row in item_rows if row[col]), 2)
            except:
                totals[col] = ''

    # Step 7: Export XLSX
    if request.method == 'POST' and 'export_xlsx' in request.form:
        import pandas as pd
        from openpyxl.utils import get_column_letter
        df_full = pd.DataFrame(records, columns=columns)
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df_full.to_excel(writer, sheet_name='Invoice_Full_Data', index=False)
            sheet = writer.sheets['Invoice_Full_Data']
            for i, col in enumerate(df_full.columns):
                column_letter = get_column_letter(i + 1)
                max_length = max(df_full[col].astype(str).map(len).max(), len(col))
                sheet.column_dimensions[column_letter].width = max_length + 2
        buf.seek(0)
        return send_file(buf, download_name=f"Invoice_{invoice_no}_full.xlsx",
                         as_attachment=True,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    # Step 8: Export PDF
    if request.method == 'POST' and 'export_pdf' in request.form:
        from weasyprint import HTML, CSS
        template_name = 'search_pdf_template_summary.html' if view_mode == 'summary' else 'search_pdf_template.html'

        rendered = render_template(template_name,
                                   item_rows=item_rows,
                                   item_columns=item_columns,
                                   common_data=common_data,
                                   totals=totals,
                                   searched=invoice_no,
                                   view_mode=view_mode)

        pdf_file = BytesIO()
        HTML(string=rendered).write_pdf(pdf_file, stylesheets=[
            CSS(string='@page { size: A3 landscape; margin: 8mm; }')
        ])
        pdf_file.seek(0)
        return send_file(pdf_file, download_name=f"Invoice_{invoice_no}_{view_mode}.pdf",
                         as_attachment=True, mimetype='application/pdf')

    # Step 9: Render HTML
    return render_template('search.html',
                            item_rows=item_rows,
                            item_columns=item_columns,
                            common_data=common_data,
                            common_columns=common_columns,
                            totals=totals,
                            searched=invoice_no,
                            view_mode=view_mode)






                           
def generate_pdf_html(common_data, item_columns, item_rows, totals, invoice_no, view_mode):
    from flask import render_template
    return render_template(
        'search_pdf_template.html',
        common_data=common_data,
        item_columns=item_columns,
        item_rows=item_rows,
        totals=totals,
        searched=invoice_no,
        view_mode=view_mode
    )   
@app.route("/delete_item", methods=["POST"])
def delete_item():
    s_no = request.form.get("S_no")

    if not s_no:
        return "Invalid deletion", 400

    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.environ["DB_PASSWORD"],
        database="inventory_db"
    )
    cursor = conn.cursor()

    # Fetch the Invoice_no before deletion for redirection
    cursor.execute("SELECT Invoice_no FROM inventory_table_samplee WHERE S_no = %s", (s_no,))
    result = cursor.fetchone()
    if not result:
        cursor.close()
        conn.close()
        return "Item not found", 404

    invoice_no = result[0]

    # HARD DELETE
    cursor.execute("DELETE FROM inventory_table_samplee WHERE S_no = %s", (s_no,))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("edit_invoice", invoice_no=invoice_no))


@app.route('/start')
def start():
    return render_template('start.html')

@app.route('/edit/<invoice_no>', methods=['GET'])
def edit_invoice(invoice_no):
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.environ["DB_PASSWORD"],
        database="inventory_db"
    )
    cursor = conn.cursor(dictionary=True)

    # Get common data
    common_data = get_common_data(invoice_no)

    # Get item rows
    cursor.execute("SELECT * FROM inventory_table_samplee WHERE Invoice_no = %s ORDER BY S_no", (invoice_no,))
    item_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('edit.html',
                           invoice_no=invoice_no,
                           common_data=common_data,
                           item_rows=item_rows,
                           metadata=common_data)  # ✅ fix for undefined error



@app.route('/update_invoice/<invoice_no>', methods=['POST'])
def update_invoice(invoice_no):
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.environ["DB_PASSWORD"],
        database="inventory_db"
    )
    cursor = conn.cursor()

    # 1. Update common fields
# Extract actual currency
    invoice_currency = request.form.get("Invoice_currency")
    if invoice_currency == "Custom":
        invoice_currency = request.form.get("Invoice_currency_custom", "").strip()

    # Now update common fields (replace Invoice_currency manually)
    common_fields = ['Invoice_date', 'PARTY_NAME', 'GRN_no', 'Material_Recieved_Date',
                    'Currency_Exchange_Rate', 'BOE_no', 'BOE_date', 'AWB_no', 'AWB_date',
                    'BOE_frieght_charges', 'Freight_Charges', 'Freight_Exchange_Rate',
                    'BOE_insurance_charges', 'BOE_insurance_percentage', 'BOE_Misc', 'Grade']

    updates = ', '.join([f"{field} = %s" for field in common_fields])
    values = [request.form.get(field) for field in common_fields]

    # Inject Invoice_currency manually at the correct spot
    updates = updates.replace("Currency_Exchange_Rate = %s", "Invoice_currency = %s, Currency_Exchange_Rate = %s")
    values.insert(common_fields.index("Currency_Exchange_Rate"), invoice_currency)


    meis_license_use = request.form.get("meis_license_use")
    meis_license_val = request.form.get("MEIS_License") if meis_license_use == "Yes" else "no"
    updates += ", MEIS_License = %s"
    values.append(meis_license_val)

    cursor.execute(f"UPDATE inventory_table_samplee SET {updates} WHERE Invoice_no = %s", values + [invoice_no])

    # 2. Handle deletions
    deleted_items = request.form.getlist('deleted_items[]')
    for s_no in deleted_items:
        cursor.execute("DELETE FROM inventory_table_samplee WHERE S_no = %s", (s_no,))

    # 3. Update existing items
    item_count = int(request.form.get("item_count", 0))
    for i in range(item_count):
        s_no = request.form.get(f"S_no_{i}")
        if not s_no or s_no in deleted_items:
            continue
        fields = {
            'Artno': request.form.get(f'Artno_{i}', '').strip(),
            'Specification': request.form.get(f'Specification_{i}', '').strip(),
            'Type_of_Product': (
                request.form.get(f'Type_of_Product_custom_{i}', '').strip()
                if request.form.get(f'Type_of_Product_{i}') == 'Custom'
                else request.form.get(f'Type_of_Product_{i}', '').strip()
            ),
            'Quantity': float(request.form.get(f'Quantity_{i}', 0) or 0),
            'qty_type': request.form.get(f'qty_type_{i}', '').strip(),
            'Rate_in_Euro': float(request.form.get(f'Rate_in_Euro_{i}', 0) or 0),
            'Duty_percentage_item': float(request.form.get(f'Duty_percentage_item_{i}', 0) or 0),
            'SW_srchrg_percent': float(request.form.get(f'SW_srchrg_percent_{i}', 0) or 0),
            'IGST_percentage': float(request.form.get(f'IGST_percentage_{i}', 0) or 0),
            'GWO': request.form.get(f'GWO_{i}', '').strip(),
        }
        update_stmt = ", ".join([f"{k} = %s" for k in fields])
        cursor.execute(f"UPDATE inventory_table_samplee SET {update_stmt} WHERE S_no = %s", list(fields.values()) + [s_no])

    # 4. Insert new item (if any)
    if request.form.get("new_item_flag") == "true":
        try:
            new_quantity = request.form.get("new_Quantity", "").strip()
            new_rate = request.form.get("new_Rate_in_Euro", "").strip()
            if new_quantity and new_rate:
                new_item = {
                    'Invoice_no': invoice_no,
                    'Artno': request.form.get('new_Artno', '').strip(),
                    'Specification': request.form.get('new_Specification', '').strip(),
                    'Type_of_Product': (
                        request.form.get('new_Type_of_Product_custom', '').strip()
                        if request.form.get('new_Type_of_Product', '') == 'Custom'
                        else request.form.get('new_Type_of_Product', '').strip()
                    ),
                    'Quantity': float(new_quantity),
                    'qty_type': request.form.get('new_qty_type', '').strip(),
                    'Rate_in_Euro': float(new_rate),
                    'Duty_percentage_item': float(request.form.get('new_Duty_percentage_item', 0) or 0),
                    'SW_srchrg_percent': float(request.form.get('new_SW_srchrg_percent', 0) or 0),
                    'IGST_percentage': float(request.form.get('new_IGST_percentage', 0) or 0),
                    'GWO': request.form.get('new_GWO', '').strip()
                }
                cursor.execute("""
                    INSERT INTO inventory_table_samplee (
                        Invoice_no, Artno, Specification, Type_of_Product,
                        Quantity, qty_type, Rate_in_Euro, Duty_percentage_item,
                        SW_srchrg_percent, IGST_percentage, GWO
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, tuple(new_item.values()))
        except ValueError as e:
            print("Skipping new item due to invalid input:", e)

    conn.commit()
    cursor.close()
    conn.close()

    recalculate_invoice(invoice_no)
    return redirect(f"/search?invoice_no={invoice_no}")




@app.route("/search_after_update/<invoice_no>")
def search_after_update(invoice_no):
    return render_template("search_redirect.html", invoice_no=invoice_no)







if __name__ == '__main__':
    app.run(debug=True)
