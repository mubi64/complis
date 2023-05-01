# Copyright (c) 2023, Sowaan and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import requests
from frappe.utils import now, add_to_date
from frappe.model.document import Document
import datetime
import hashlib
import hmac


class ComplisSite(Document):
    pass


@frappe.whitelist()
def sync_invoices():
    complis_sites = frappe.get_all("Complis Site", filters={"enabled": 1})
    if (len(complis_sites) == 0):
        frappe.throw(
            _("Complis sites not found. Please make atleast one complis site and try again")
        )

    for x in complis_sites:
        site = frappe.get_doc("Complis Site", x)
        sync_invoice_for_single_site(site)

    return "Success"


def sync_invoice_for_single_site(site):
    get_invoices_from_complis(site)


def get_invoices_from_complis(site):
    dt = datetime.datetime.strptime(str(site.synced_till), "%Y-%m-%d %H:%M:%S")
    fromdate = dt.strftime("%Y-%-m-%-dT%H:%M:%S.%f")[:-3] + 'Z'
    secret = site.secret_key
    myEncoder = 'utf-8'
    Key = str(fromdate).encode(myEncoder)
    Text = str(secret).encode(myEncoder)

    myHMACSHA256 = hmac.new(Key, Text, hashlib.sha256)
    HashCode = myHMACSHA256.digest()
    hash = ''.join('{:02x}'.format(b) for b in HashCode)
    calculatedSecret = hash.upper()
    data = {
        "date_from": str(fromdate),
        "date_to": str(datetime.datetime.now().strftime("%Y-%-m-%-dT%H:%M:%S.%f")[:-3] + 'Z'),
        "key": calculatedSecret
    }

    print(data, "My data List")

    # sync_from = site.synced_till

    # while (1 == 1):
    try:
        r = requests.post(site.complis_site_url, json=data).json()
    except requests.exceptions.HTTPError:
        button_label = frappe.bold(_("Get Access Token"))
        frappe.throw(
            (
                "Something went wrong during the people sync. Click on {0} to generate a new one."
            ).format(button_label)
        )

    invoices = r.get("data")
    itrableInvoices = {}
    for invoice in invoices:
        invoice_no = invoice['invoice_no']
        items = invoice['Item_List']
        if any(item['item_qty'] == 0 for item in items):
            continue
            # invoices.remove(invoice)
        # for item in items:
        #     if item.get('item_qty') == 0:
        #         # # print(item.item_qty, "Item QTY Print")
        #         # if (len(items) > 0):
        #         #     items.remove(item)
        #         # else:
        #         invoices.remove(invoice)

        if invoice_no in itrableInvoices:
            itrableInvoices[invoice_no]['Item_List'].extend(items)
        else:
            itrableInvoices[invoice_no] = invoice

    result = list(itrableInvoices.values())
    # print(invoices, "Check Invoices")
    last_invoice = insert_invoices_from_complis(result, site)
    # sync_from = last_invoice.get("invoice_date")

    # if r.get("next") is None:
    #     break

    frappe.msgprint(
        msg=_(
            "<b style='color:green'>"+site.complis_site_url +
            "</b>: Invoices synced successfully!"
        )
    )


def insert_invoices_from_complis(invoices, site):
    curr_invoice = {}
    for x in invoices:
        erp_invoices = frappe.get_all("Sales Invoice", filters={
            "complis_record_id": x.get("invoice_no")
        })
        print(x.get("invoice_no"), "Invoice No Print")
        # if length is more than 0 then this invoice is already synced with erp
        if (len(erp_invoices) == 0):
            curr_invoice = x

            erp_customer = site.default_customer
            erp_items = None

            # check customer from erp
            if (curr_invoice.get("customer_name_en") is not None):
                customer_name = curr_invoice.get("customer_name_en")
                erp_customer = get_erp_customer(
                    customer_name, site, curr_invoice)

            # check items from erp
            if (len(curr_invoice.get("Item_List")) > 0):
                items = curr_invoice.get("Item_List")
                erp_items = get_erp_items(items, site)

            sales_tax_template = site.sales_tax_template
            # if tax template is not defined in the complis settings then use default one
            if sales_tax_template is None:
                default_tax_templates = frappe.get_all("Sales Taxes and Charges Template",
                                                       filters={
                                                           "is_default": 1
                                                       }
                                                       )
                if (len(default_tax_templates) > 0):
                    sales_tax_template = default_tax_templates[0].name
            si = frappe.new_doc("Sales Invoice")
            si.customer = erp_customer
            si.set_posting_time = 1
            si.posting_date = curr_invoice.get("invoice_date")
            si.due_date = curr_invoice.get("invoice_date")
            si.complis_record_id = curr_invoice.get("invoice_no")
            si.complis_invoice_number = curr_invoice.get("invoice_no")
            si.taxes_and_charges = sales_tax_template
            si.debit_to = site.receivable_account
            si.update_stock = 0
            si.set_warehouse = site.warehouse

            # link cost center to invoice if provided in complis site configuration
            if site.cost_center is not None:
                si.cost_center = site.cost_center

            # for i in curr_invoice.get("payments"):
            # 	si.is_pos = 1
            # 	method_name = i.get("description")
            # 	for j in site.complis_to_erp_mode_of_payment_mapping:
            # 		if method_name == j.complis_mode_of_payment:
            # 			print("*********payment amount************")
            # 			print(i.get("amount"))
            # 			si.append("payments", {
            # 				"mode_of_payment": j.erp_mode_of_payment,
            # 				"amount": i.get("amount_cents")/100
            # 			})
            # 			break
            rate = 0
            for i in curr_invoice.get("Item_List"):
                db_items = frappe.get_all("Item", filters={
                    "name": i.get("item_desc_en").strip()
                })
                if (len(db_items) > 0):
                    erp_item = db_items[0]
                    discount = 0
                    rate = float(i.get("item_price"))
                    # if i.get("item_qty") is not None:
                    #     rate = rate * float(i.get("item_qty"))
                    # for dis in i.get("adjustments"):
                    # 	if dis.get("type") == "Discount":
                    # 		discount += dis.get("amount_cents")

                    # print('******DISCOUNT*******')
                    # print(str(round(discount/100,2)))
                    si.append("items", {
                        "item_code": erp_item.name,
                        "rate": round(rate, 2) / int(i.get("item_qty")),
                        "qty": i.get("item_qty")
                    })
                    rate += rate

            if rate < 0:
                si.is_return = 1
                si.naming_series = site.sales_return_series
            si.set_missing_values()
    #         print(str(x.get("id"))+":" +
    #               curr_invoice.get("invoice_date")+":"+str(erp_customer))
            si.insert(ignore_permissions=True)

    #         # this below code is to submit the invoice,
    #         # we will do once the integration would be stable

    #         # si.docstatus = 1
    #         # si.posting_date = curr_invoice.get("invoice_date")
    #         # si.save()

    if curr_invoice:
        site.synced_till = curr_invoice.get("invoice_date")
        site.save()
        frappe.db.commit()
    return curr_invoice


def get_erp_customer(customer_name, site, curr_invoice):
    erp_customer = frappe.get_all("Customer", filters={
        "customer_name": customer_name
    })
    if (len(erp_customer) == 0):
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "complis_customer_id": curr_invoice.get("customer_name_en"),
                "customer_name": curr_invoice.get("customer_name_en"),
                "customer_name_in_arabic": curr_invoice.get("customer_name_ar"),
                "customer_group": "All Customer Groups",
                "territory": "All Territories",
                # "address_line1": people.get("address")
            }
        ).insert(ignore_permissions=True)

        frappe.db.commit()
        return customer.name

    return erp_customer[0].name


def get_erp_items(items, site):
    erp_items = []
    for x in items:
        product_id = x.get("item_desc_en")
        items_in_db = frappe.get_all("Item",
                                     filters={
                                         "complis_item_code": product_id
                                     },
                                     fields=['name', 'complis_item_code']
                                     )
        if (len(items_in_db) == 0):
            # item is not present in erp by complis code, lets try with item name
            item = None
            if (not frappe.db.exists("Item", {"name": x.get("item_desc_en")})):
                item = frappe.get_doc(
                    {
                        "doctype": "Item",
                        "item_code": x.get("item_desc_en"),
                        "complis_item_code": x.get("item_desc_en"),
                        "item_name": x.get("item_desc_en"),
                        "item_group": "All Item Groups",
                        "stock_uom": "Nos",
                        "is_stock_item": 1,
                        "standard_rate": x.get("item_price")
                    }
                ).insert(ignore_permissions=True)
            else:
                item = frappe.get_doc("Item", x.get("item_desc_en"))
                if (item.complis_item_code == None):
                    item.complis_item_code = x.get("item_desc_en")
                item.save()

            erp_items.append({
                "name": item.name,
                "complis_item_code": item.complis_item_code
            })
        else:
            erp_items.append({
                "name": items_in_db[0].get("name"),
                "complis_item_code": items_in_db[0].get("complis_item_code")
            })

    frappe.db.commit()
    return erp_items
