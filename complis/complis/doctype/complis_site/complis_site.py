# Copyright (c) 2023, Sowaan and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import requests
from frappe.utils import now, add_to_date
from frappe.model.document import Document
from frappe.utils.file_manager import save_url, save_file
from datetime import datetime, timedelta
import hashlib
import hmac


class ComplisSite(Document):
    pass


def get_complis_list():
    complis_sites = frappe.get_all("Complis Site", filters={"enabled": 1})

    if not complis_sites:
        frappe.throw(_("No Complis sites found. Please create at least one site and try again"))

    return complis_sites


@frappe.whitelist()
def sync_invoices_with_scheduler():
    complis_sites = get_complis_list()
    sync_date = datetime.now() - timedelta(days=15)
    sync_date_str = sync_date.strftime("%Y-%m-%d %H:%M:%S")
    synced_date = datetime.strptime(sync_date_str, "%Y-%m-%d %H:%M:%S")

    for site_data in complis_sites:
        site = frappe.get_doc("Complis Site", site_data.name)
        get_invoices_from_complis(site, synced_date, datetime.now())

    return "Success"


@frappe.whitelist()
def sync_pr_invoices_with_scheduler():
    complis_sites = get_complis_list()
    sync_date = datetime.now() - timedelta(days=30)
    sync_date_str = sync_date.strftime("%Y-%m-%d %H:%M:%S")
    synced_date = datetime.strptime(sync_date_str, "%Y-%m-%d %H:%M:%S")


    for site_data in complis_sites:
        doc = frappe.get_doc("Complis Site", site_data.name)
        data = {
            "date_from": str(synced_date),
            "date_to": str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "Secret": doc.pr_secret_key
        }
        get_purchase_invoices_from_complis(doc, data)

    return "Success"

@frappe.whitelist()
def sync_invoices():
    complis_sites = get_complis_list()

    for site_data in complis_sites:
        site = frappe.get_doc("Complis Site", site_data.name)
        get_invoices_from_complis(site, site.synced_till, site.synced_to)

    return "Success"

@frappe.whitelist()
def sync_purchase_invoices():
    complis_sites = get_complis_list()

    for site_data in complis_sites:
        doc = frappe.get_doc("Complis Site", site_data.name)
        data = {
            "date_from": str(doc.sync_start),
            "date_to": str(doc.sync_end),
            "Secret": doc.pr_secret_key
        }
        print(data, "check \n\n\n\n\n")
        get_purchase_invoices_from_complis(doc, data)

    return "Success"


def get_purchase_invoices_from_complis(doc, data):
    try:
        res = requests.post(doc.purchase_site_url, json=data).json()
    except requests.exceptions.HTTPError:
        button_label = frappe.bold(_("Get Access Token"))
        frappe.throw(
            (
                "Something went wrong during the people sync. Click on {0} to generate a new one."
            ).format(button_label)
        )

    invoices = res.get("data")
    insert_pr_invoices_from_complis(doc, invoices)
    frappe.msgprint(
        msg=_(
            "<b style='color:green'>" + doc.purchase_site_url +
            "</b>: Invoices synced successfully!"
        )
    )




def insert_pr_invoices_from_complis(doc, invoices):
    post_date = datetime.now()
    for inv in invoices:
        supplier = ""
        pr_invoices = frappe.get_all("Purchase Invoice", filters={
            "bill_no": inv.get("invoice_no")
        })
        # if length is more than 0 then this invoice is already synced with erp
        if (len(pr_invoices) == 0):
            if (inv.get("supplier_code") is not None):
                supplier_code = inv.get("supplier_code").strip()
                supplier = get_supplier(doc, supplier_code, inv)
                
            if inv.get("supplier_address_en"):
                get_pr_address(supplier, inv)

            if (len(inv.get("Item_List")) > 0):
                    items = inv.get("Item_List")
                    get_pr_items(items, doc)

            sales_tax_template = doc.sales_tax_template
            # if tax template is not defined in the complis settings then use default one
            if sales_tax_template is None:
                default_tax_templates = frappe.get_all("Sales Taxes and Charges Template", filters={"is_default": 1})
                if (len(default_tax_templates) > 0):
                    sales_tax_template = default_tax_templates[0].name

            post_date = datetime.strptime(inv.get("invoice_date"), "%d-%m-%Y")
            due_date = datetime.strptime(inv.get("invoice_due"), "%d-%m-%Y")
            pi = frappe.get_doc({
                "doctype": "Purchase Invoice",
                "supplier": supplier,
                "set_posting_time": 1,
                "posting_date": post_date.strftime("%Y-%m-%d"),
                "due_date": due_date.strftime("%Y-%m-%d"),
                "bill_no": inv.get("invoice_no"),
                "taxes_and_charges": sales_tax_template,
                "credit_to": doc.credit_to,
                "total_taxes_and_charges": inv.get("total_tax"),
                "invoice_acc_no": inv.get("invoice_acc_no"),
                "set_warehouse": doc.purchase_warehouse
            })
          
            if doc.company:
                pi.company = doc.company

            # link cost center to invoice if provided in complis site configuration
            if doc.cost_center:
                pi.cost_center = doc.cost_center

            rate = 0
            for i in inv.get("Item_List"):
                db_items = frappe.get_all("Item", filters={
                    "name": i.get("item_name").strip()
                }, fields=["name"])
                if (len(db_items) > 0):
                    erp_item = db_items[0]
                    rate = float(i.get("item_price"))
                    pi.append("items", {
                        "item_code": erp_item.name,
                        "rate": round(rate, 2) / int(i.get("item_qty")),
                        "qty": i.get("item_qty")
                    })

            tax_template = frappe.get_doc("Sales Taxes and Charges Template", sales_tax_template)

            for tax in tax_template.taxes:
                pi.append("taxes", {
                    "charge_type": tax.charge_type,
                    "account_head": tax.account_head,
                    "description": tax.description,
                    "cost_center": tax.cost_center,
                    "rate": tax.rate
                })

            if float(i.get("item_qty")) < 0 or i.get("item_qty") == "Yes":
                pi.is_return = 1
                pi.naming_series = doc.sales_return_series
                return_pr_invoices = frappe.get_all("Purchase Invoice", filters={
                    "bill_no": inv.get("return_against")
                })

                if len(return_pr_invoices) > 0:
                    pi.return_against = return_pr_invoices[0].name
            else:
                pi.naming_series = doc.sales_invoice_series
            # print(pi.posting_date, pi.due_date, pi.bill_no, "\n\n\n\n\n\n")
            pi.set_missing_values()
            pi.insert(ignore_permissions=True)
            for attac in inv.get("attachments"):
                link = attac.get("download_link")
                print(link, inv.get("supplier_code"), "check Link \n\n\n\n\n\n\n")
                if link:
                    name = link.split("/")
                    file_name = name[len(name) - 1]

                    # Save the file
                    file_url = save_url(link, file_name, pi.doctype, pi.name, "Home/Attachments", 0)
                    print(file_url, "check Name")
                # Add the file to the document
            #     pi.append('attachments', {
            #         'file_url': file_url,
            #         'file_name': file_name
            #     })

            #     # Save the document
            # pi.save()


    if inv:
        doc.sync_start = post_date.strftime("%Y-%m-%d")
        doc.sync_end = datetime.strptime(str(post_date.strftime("%Y-%m-%d")), "%Y-%m-%d") + timedelta(days=30)
        doc.save()
        frappe.db.commit()
    return inv
            

def get_invoices_from_complis(site, synced_date, to_date):
    fromdate = synced_date.strftime("%Y-%m-%-dT%H:%M:%S.%f")[:-3] + 'Z'
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
        "date_to": str(to_date.strftime("%Y-%m-%-dT%H:%M:%S.%f")[:-3] + 'Z'),
        "key": calculatedSecret
    }
    print(data, "My data List \n\n\n\n\n\n\n\n")

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
    filtered_invoices = filter_invoices(invoices)
    last_invoice = insert_invoices_from_complis(filtered_invoices, site)

    frappe.msgprint(
        msg=_(
            "<b style='color:green'>"+site.complis_site_url +
            "</b>: Invoices synced successfully!"
        )
    )


def insert_invoices_from_complis(invoices, site):
    for c_inv in invoices:
        erp_invoices = frappe.get_all("Sales Invoice", filters={
            "complis_record_id": c_inv.get("invoice_no")
        })
        # if length is more than 0 then this invoice is already synced with erp
        if (len(erp_invoices) == 0):

            erp_customer = site.default_customer

            # check customer from erp
            customer_name = c_inv.get("customer_code").strip()
            if (customer_name is not None):
                erp_customer = get_erp_customer(customer_name, site, c_inv)

            if c_inv.get("customer_address_en"):
                get_erp_address(c_inv.get("invoice_no").strip(), erp_customer, c_inv)
                
            # check items from erp
            items = c_inv.get("Item_List")
            if len(items) > 0:
                get_erp_items(items, site)

            sales_tax_template = site.sales_tax_template or get_default_tax_template()
            
            si = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": erp_customer,
                "set_posting_time": 1,
                "posting_date": c_inv.get("invoice_date"),
                "due_date": c_inv.get("invoice_due"),
                "complis_record_id": c_inv.get("invoice_no"),
                "complis_invoice_number": c_inv.get("invoice_no"),
                "taxes_and_charges": sales_tax_template,
                "debit_to": site.receivable_account,
                "update_stock": 0,
                "set_warehouse": site.warehouse,
                "total_foreign_currency": c_inv.get("total_foreign_currency"),
                "total_excl_tax": c_inv.get("total_excl_tax_fc"),
                "total_tax": c_inv.get("total_tax_fc"),
                "total_incl_tax": c_inv.get("total_incl_tax_fc")
            })
            
            if site.company:
                si.company = site.company

            # link cost center to invoice if provided in complis site configuration
            if site.cost_center:
                si.cost_center = site.cost_center

            rate = 0
            for i in c_inv.get("Item_List"):
                db_items = frappe.get_all("Item", filters={"name": i.get("item_desc_en").strip()}, fields=["name", "purchase_order_no"])
                if len(db_items) > 0:
                    erp_item = db_items[0]
                    rate = float(i.get("item_price"))
                    si.append("items", {
                        "item_code": erp_item.naxme,
                        "complis_item_no": i.get("sr_no"),
                        "purchase_order_no": i.get("customer_order_no"),
                        "rate": round(rate, 2) / int(i.get("item_qty")),
                        "qty": i.get("item_qty")
                    })

            si.is_return = 1 if float(i.get("item_qty")) < 0 else 0
            si.naming_series = site.sales_return_series if si.is_return else site.sales_invoice_series

            si.set_missing_values()
            si.insert(ignore_permissions=True)

    if c_inv:
        site.synced_till = c_inv.get("invoice_date")
        site.synced_to = datetime.strptime((c_inv.get("invoice_date")+" 00:00:00.000000"), "%Y-%m-%d %H:%M:%S.%f") + timedelta(days=3)
        site.save()
        frappe.db.commit()

    return c_inv


def get_erp_address(address_name, customer_name, curr_invoice):
    erp_address = frappe.get_all("Address", filters={"address_title": customer_name},)
    
    if len(erp_address) == 0:
        address = frappe.get_doc({
            "doctype": "Address",
            "address_title": customer_name,
            "address_line1": curr_invoice.get("customer_street_name_en") or "---",
            "address_line2": curr_invoice.get("customer_building_no_en"),
            "country": curr_invoice.get("customer_country_en"),
            "pincode": curr_invoice.get("customer_postal_code_en"),
            "phone": curr_invoice.get("customer_contact_no_en"),
            "city": curr_invoice.get("customer_city_en") or "---"
        })

        address.append("links", {
            'link_doctype': "Customer",
            'link_name': customer_name,
            'link_title': customer_name
        })
        address.insert(ignore_permissions=True)

        frappe.db.commit()
        return address.name
    
    return erp_address[0].name


def get_pr_address(supplier, inv):
    erp_address = frappe.get_all("Address", filters={"address_title": supplier})

    if len(erp_address) == 0:
        address = frappe.get_doc({
            "doctype": "Address",
            "address_title": supplier,
            "address_line1": inv.get("supplier_address_en") or "---",
            "city": inv.get("supplier_city_en") or "---"
        })

        address.append("links", {
            'link_doctype': "Supplier",
            'link_name': supplier,
        })
        address.insert(ignore_permissions=True)

        frappe.db.commit()
        return address.name
    
    return erp_address[0].name


def get_erp_customer(customer_name, site, curr_invoice):
    erp_customer = frappe.get_all("Customer", filters={"complis_customer_id": customer_name})
    
    if len(erp_customer) == 0:
        customer = frappe.get_doc({
            "doctype": "Customer",
            "complis_customer_id": curr_invoice.get("customer_code"),
            "customer_name": curr_invoice.get("customer_name_en"),
            "customer_number": curr_invoice.get("customer_code"),
            "customer_name_in_arabic": curr_invoice.get("customer_name_ar"),
            "txt_id": curr_invoice.get("customer_vat_no"),
            "customer_group": "All Customer Groups",
            "territory": "All Territories",
        }).insert(ignore_permissions=True)

        frappe.db.commit()
        return customer.name

    return erp_customer[0].name


def get_supplier(doc, code, inv):
    erp_supplier = frappe.get_all("Supplier", filters={"supplier_no": code})

    if len(erp_supplier) == 0:
        supplier = frappe.get_doc({
            "doctype": "Supplier",
            "supplier_name": inv.get("supplier_name_en"),
            "supplier_name_in_arabic": inv.get("supplier_name_ar"),
            "supplier_no": code,
            "txt_id": inv.get("supplier_vat_no"),
            "supplier_group": doc.supplier_group,
            "supplier_type": doc.supplier_type,
        }).insert(ignore_permissions=True)

        frappe.db.commit()
        return supplier.name

    return erp_supplier[0].name


def get_erp_items(items, site):
    for x in items:
        product_id = x.get("item_desc_en").strip()
        items_in_db = frappe.get_all("Item", filters={"complis_item_code": product_id}, fields=['name'])

        if len(items_in_db) == 0:
            if frappe.db.exists("Item", {"name": product_id}):
                item = frappe.get_doc("Item", product_id)
                if (item.complis_item_code == None):
                    item.complis_item_code = product_id
                    item.save()
            else:
                item = frappe.get_doc({
                    "doctype": "Item",
                    "item_code": product_id,
                    "complis_item_code": product_id,
                    "complis_item_no": x.get("sr_no"),
                    "item_name": product_id,
                    "item_group": "All Item Groups",
                    "stock_uom": "Nos",
                    "is_stock_item": 0,
                    "standard_rate": x.get("item_price"),
                    "purchase_order_no": x.get("customer_order_no")
                }).insert(ignore_permissions=True)
                frappe.db.commit()

    return "Success"


def get_pr_items(items, doc):
    for x in items:
        item_name = x.get("item_name").strip()
        items_in_db = frappe.get_all("Item", filters={"name": item_name}, fields=['name'])
        
        if len(items_in_db) == 0:
            frappe.get_doc({
                "doctype": "Item",
                "item_code": item_name,
                "item_name": item_name,
                "item_group": doc.item_group,
            }).insert(ignore_permissions=True)
            frappe.db.commit()

    return "Success"



def filter_invoices(invoices):
    filtered_invoices = {}

    for invoice in invoices:
        if any(item['item_qty'] == 0 for item in invoice['Item_List']):
            continue

        invoice_no = invoice['invoice_no']
        items = invoice['Item_List']

        if invoice_no in filtered_invoices:
            filtered_invoices[invoice_no]['Item_List'].extend(items)
        else:
            filtered_invoices[invoice_no] = invoice

    return list(filtered_invoices.values())


def get_default_tax_template():
    return frappe.get_value("Sales Taxes and Charges Template", {"is_default": 1})

