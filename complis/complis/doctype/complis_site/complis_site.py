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
def sync_invoices_with_scheduler():
    complis_sites = frappe.get_all("Complis Site", filters={
                                   "enabled": 1}, fields=["*"])
    if (len(complis_sites) == 0):
        frappe.throw(
            _("Complis sites not found. Please make atleast one complis site and try again")
        )

    for x in complis_sites:
        site = frappe.get_doc("Complis Site", x)
        synced_date = datetime.datetime.strptime(
            str(site.synced_till), "%Y-%m-%d %H:%M:%S")
        get_invoices_from_complis(site, synced_date, datetime.datetime.now())

    return "Success"


@frappe.whitelist()
def sync_invoices():
    complis_sites = frappe.get_all("Complis Site", filters={"enabled": 1})
    if (len(complis_sites) == 0):
        frappe.throw(
            _("Complis sites not found. Please make atleast one complis site and try again")
        )

    for x in complis_sites:
        site = frappe.get_doc("Complis Site", x)
        synced_date = datetime.datetime.strptime(
            str(site.synced_till), "%Y-%m-%d %H:%M:%S")
        to_date = datetime.datetime.strptime(
            str(site.synced_to), "%Y-%m-%d %H:%M:%S")
        get_invoices_from_complis(site, synced_date, to_date)

    return "Success"

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

    # print(data, "My data List")

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

    if invoices != None:
        for invoice in invoices:
            invoice_no = invoice['invoice_no']
            items = invoice['Item_List']
            unique_objects = []
            seen_srnos = set()
            if any(item['item_qty'] == 0 for item in items):
                continue

            if invoice_no in itrableInvoices:
                itrableInvoices[invoice_no]['Item_List'].extend(
                    items)  # Assign unique_objects to Item_List
            else:
                itrableInvoices[invoice_no] = invoice

            for obj in itrableInvoices[invoice_no]['Item_List']:
                sr_no = obj['sr_no']
                if sr_no not in seen_srnos:
                    unique_objects.append(obj)
                    seen_srnos.add(sr_no)
            itrableInvoices[invoice_no]['Item_List'] = unique_objects

        result = list(itrableInvoices.values())
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
        # if length is more than 0 then this invoice is already synced with erp
        if (len(erp_invoices) == 0):
            curr_invoice = x

            erp_customer = site.default_customer

            # check customer from erp
            if (curr_invoice.get("customer_name_en") is not None):
                customer_name = curr_invoice.get("customer_name_en").strip()
                erp_customer = get_erp_customer(
                    customer_name, site, curr_invoice)

            if curr_invoice.get("customer_address_en"):
                address_name = curr_invoice.get("invoice_no")
                customer_name = curr_invoice.get("customer_name_en")
                get_erp_address(
                    address_name, customer_name, curr_invoice)
            # check items from erp
            if (len(curr_invoice.get("Item_List")) > 0):
                items = curr_invoice.get("Item_List")
                get_erp_items(items, site)

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
            si.due_date = curr_invoice.get("invoice_due")
            si.complis_record_id = curr_invoice.get("invoice_no")
            si.complis_invoice_number = curr_invoice.get("invoice_no")
            si.taxes_and_charges = sales_tax_template
            si.debit_to = site.receivable_account
            si.update_stock = 0
            si.set_warehouse = site.warehouse

            if site.company:
                si.company = site.company

            # link cost center to invoice if provided in complis site configuration
            if site.cost_center:
                si.cost_center = site.cost_center

            rate = 0
            for i in curr_invoice.get("Item_List"):
                db_items = frappe.get_all("Item", filters={
                    "name": i.get("item_desc_en").strip()
                })
                if (len(db_items) > 0):
                    erp_item = db_items[0]
                    discount = 0
                    rate = float(i.get("item_price"))
                    si.append("items", {
                        "item_code": erp_item.name,
                        "rate": round(rate, 2) / int(i.get("item_qty")),
                        "qty": i.get("item_qty")
                    })
                    rate += rate

            if rate < 0:
                si.is_return = 1
                si.naming_series = site.sales_return_series
            else:
                si.naming_series = site.sales_invoice_series
            si.set_missing_values()
            si.insert(ignore_permissions=True)

            # this below code is to submit the invoice,
            # we will do once the integration would be stable

            # si.docstatus = 1
            # si.posting_date = curr_invoice.get("invoice_date")
            # si.save()

    if curr_invoice:
        site.synced_till = curr_invoice.get("invoice_date")
        site.synced_to = datetime.datetime.strptime((curr_invoice.get("invoice_date")+" 00:00:00.000000"), "%Y-%m-%d %H:%M:%S.%f") + datetime.timedelta(days=5)
        site.save()
        frappe.db.commit()
    return curr_invoice


def get_erp_address(address_name, customer_name, curr_invoice):
    # erp_address = frappe.db.sql(""" SELECT name, links FROM `tabAddress` """)
    erp_address = frappe.get_all("Address", filters={
        "address_title": customer_name,
    }, fields=["*"])
    if len(erp_address) == 0:
        if (not frappe.db.exists("Item", {"address_title": customer_name})):
            address = frappe.get_doc(
                {
                    "doctype": "Address",
                    "address_title": customer_name,
                    "address_line1": curr_invoice.get("customer_street_name_en") if curr_invoice.get("customer_street_name_en") != "" else "---",
                    "address_line2": curr_invoice.get("customer_building_no_en"),
                    # "address_in_arabic": curr_invoice.get("customer_address_ar"),
                    "country": curr_invoice.get("customer_country_en"),
                    "pincode": curr_invoice.get("customer_postal_code_en"),
                    "phone": curr_invoice.get("customer_contact_no_en"),
                }
            )

            if curr_invoice.get("customer_city_en") != "":
                address.city = curr_invoice.get("customer_city_en")
            else:
                address.city = "--"

            address.append("links", {
                'link_doctype': "Customer",
                'link_name': customer_name,
                'link_title': customer_name
            })
            address.insert(ignore_permissions=True)

            frappe.db.commit()
            return address.name

def get_erp_customer(customer_name, site, curr_invoice):
    customer = {}
    erp_customer = frappe.get_all("Customer", filters={
        "name": customer_name
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
            }
        ).insert(ignore_permissions=True)

        frappe.db.commit()
        return customer.name

    return erp_customer[0].name


def get_erp_items(items, site):
    for x in items:
        product_id = x.get("item_desc_en").strip()
        items_in_db = frappe.get_all("Item",
                                     filters={
                                         "complis_item_code": product_id
                                     },
                                     fields=['name', 'complis_item_code']
                                     )
        if (len(items_in_db) == 0):
            # item is not present in erp by complis code, lets try with item name
            item = None
            if frappe.db.exists("Item", {"name": product_id}):
                item = frappe.get_doc("Item", product_id)
                if (item.complis_item_code == None):
                    item.complis_item_code = product_id
                item.save()
            else:
                item = frappe.get_doc(
                    {
                        "doctype": "Item",
                        "item_code": product_id,
                        "complis_item_code": product_id,
                        "item_name": product_id,
                        "item_group": "All Item Groups",
                        "stock_uom": "Nos",
                        "is_stock_item": 0,
                        "include_item_in_manufacturing": 0,
                        "item_group": "Services",
                        "standard_rate": x.get("item_price")
                    }
                ).insert(ignore_permissions=True)
                frappe.db.commit()

    return "Success"
