import os
from decimal import Decimal, ROUND_HALF_UP
import mysql.connector

def recalculate_invoice(invoice_no):
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.environ["DB_PASSWORD"],
        database="inventory_db"
    )
    cursor = conn.cursor(dictionary=True)

    # --- Fetch all item rows ---
    cursor.execute("SELECT * FROM inventory_table_samplee WHERE Invoice_no = %s", (invoice_no,))
    item_rows = cursor.fetchall()
    if not item_rows:
        print("No items found for invoice:", invoice_no)
        return

    # --- Common fields ---
    common = item_rows[0]

    # Currency (already saved in DB as 'Invoice_currency' — dropdown OR custom already handled during save)
    currency_exchange_rate = Decimal(str(common.get('Currency_Exchange_Rate') or 0))
    freight_charges = Decimal(str(common.get('Freight_Charges') or 0))
    freight_ex_rate = Decimal(str(common.get('Freight_Exchange_Rate') or 0))
    boe_misc = Decimal(str(common.get('BOE_Misc') or 0))

    # Correct freight calculation from user input
    boe_freight = (freight_charges * freight_ex_rate).quantize(Decimal("0.01"))

    insurance_pct = Decimal(str(common.get('BOE_insurance_percentage') or 0))
    boe_insurance = Decimal(str(common.get('BOE_insurance_charges') or 0))

    # --- Material cost calculation ---
    matcost_euro_list = [Decimal(str(item['Quantity'])) * Decimal(str(item['Rate_in_Euro'])) for item in item_rows]
    matcost_grn_list = [euro * currency_exchange_rate for euro in matcost_euro_list]
    total_matcost_grn = sum(matcost_grn_list)

    # --- Compute insurance from percentage if missing ---
    if boe_insurance == 0 and insurance_pct > 0 and total_matcost_grn > 0:
        boe_insurance = (total_matcost_grn * insurance_pct / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # --- Update insurance and freight values in DB ---
    cursor.execute("""
        UPDATE inventory_table_samplee
        SET BOE_insurance_charges = %s,
            BOE_insurance_percentage = %s,
            Freight = %s,
            BOE_frieght_charges = %s
        WHERE Invoice_no = %s
    """, (boe_insurance, insurance_pct, boe_freight, boe_freight, invoice_no))

    # --- Recalculate per item ---
    for item in item_rows:
        quantity = Decimal(str(item['Quantity']))
        rate_euro = Decimal(str(item['Rate_in_Euro']))
        rate_in_inr = (rate_euro * currency_exchange_rate).quantize(Decimal("0.01"))
        material_cost = (quantity * rate_euro).quantize(Decimal("0.01"))
        material_cost_grn = (material_cost * currency_exchange_rate).quantize(Decimal("0.01"))

        freight = (material_cost_grn / total_matcost_grn * boe_freight).quantize(Decimal("0.01")) if total_matcost_grn else Decimal("0")
        insurance = (material_cost_grn / total_matcost_grn * boe_insurance).quantize(Decimal("0.01")) if total_matcost_grn else Decimal("0")

        total_ass_val = (material_cost_grn + freight + insurance + boe_misc).quantize(Decimal("0.01"))
        customs_duty = (total_ass_val * Decimal(str(item['Duty_percentage_item'])) / 100).quantize(Decimal("0.01"))
        sw_srchrg_value = (customs_duty * Decimal(str(item['SW_srchrg_percent'])) / 100).quantize(Decimal("0.01"))
        total_duty = (customs_duty + sw_srchrg_value).quantize(Decimal("0.01"))

        total_ass_n_cd = (total_ass_val + total_duty).quantize(Decimal("0.01"))
        igst_value = (total_ass_n_cd * Decimal(str(item['IGST_percentage'])) / 100).quantize(Decimal("0.01"))

        Inward_Total_Value_w_IGST = (material_cost_grn + total_duty).quantize(Decimal("0.01"))
        inward_total_duty_n_igst = (total_duty + igst_value).quantize(Decimal("0.01"))

        percent_of_cd = (total_duty / material_cost_grn * 100).quantize(Decimal("0.01")) if material_cost_grn else Decimal("0.00")
        import_duty_igst_percent = (inward_total_duty_n_igst / material_cost_grn * 100).quantize(Decimal("0.01")) if material_cost_grn else Decimal("0.00")

        cursor.execute("""
            UPDATE inventory_table_samplee SET 
                Rate_in_Inr = %s,
                Material_Cost = %s,
                Materialcost_GRN = %s,
                Freight = %s,
                Insurance = %s,
                Total_Ass_Value = %s,
                Customs_Duty = %s,
                SW_srchrg_Value = %s,
                Total_Duty = %s,
                Total_Ass_n_CD = %s,
                IGST_Value = %s,
                Inward_Total_Value_w_IGST = %s,
                Inward_total_duty_n_IGST = %s,
                percent_of_CD = %s,
                Import_Duty_n_IGST_percent = %s
            WHERE S_no = %s
        """, (
            rate_in_inr,
            material_cost,
            material_cost_grn,
            freight,
            insurance,
            total_ass_val,
            customs_duty,
            sw_srchrg_value,
            total_duty,
            total_ass_n_cd,
            igst_value,
            Inward_Total_Value_w_IGST,
            inward_total_duty_n_igst,
            percent_of_cd,
            import_duty_igst_percent,
            item['S_no']
        ))

    conn.commit()
    cursor.close()
    conn.close()
