from . import __version__ as app_version

app_name = "complis"
app_title = "Complis"
app_publisher = "Sowaan"
app_description = "SowaanERP integration with complis"
app_email = "info@sowaan.com"
app_license = "MIT"

fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            [
                "fieldname",
                "in",
                (
                    "customer_name", "customer_name_in_arabic", "customer_number", "complis_customer_id", "complis_invoice_number", "complis_record_id", "complis_item_code", "complis_item_no", "purchase_order_no", "foreign_currency_details", "total_foreign_currency", "total_excl_tax", "column_break_s5imf", "total_tax", "total_incl_tax"
                )
            ]
        ]
    },
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/complis/css/complis.css"
# app_include_js = "/assets/complis/js/complis.js"

# include js, css files in header of web template
# web_include_css = "/assets/complis/css/complis.css"
# web_include_js = "/assets/complis/js/complis.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "complis/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# "Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# "methods": "complis.utils.jinja_methods",
# "filters": "complis.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "complis.install.before_install"
# after_install = "complis.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "complis.uninstall.before_uninstall"
# after_uninstall = "complis.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "complis.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# "Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# "ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# "*": {
# "on_update": "method",
# "on_cancel": "method",
# "on_trash": "method"
# }
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
    # "cron": {
    # 	"* * * * *": [
    # 		"complis.complis.doctype.complis_site.complis_site.sync_invoices"
    # 	],
    # },
    # "all": [
    # 	"complis.tasks.all"
    # ],
    # "daily": [
    # 	"complis.tasks.daily"
    # ],
    "hourly": [
        "complis.complis.doctype.complis_site.complis_site.sync_invoices_with_scheduler"
    ],
    # "weekly": [
    # 	"complis.tasks.weekly"
    # ],
    # "monthly": [
    # 	"complis.tasks.monthly"
    # ],
}

# Testing
# -------

# before_tests = "complis.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# "frappe.desk.doctype.event.event.get_events": "complis.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# "Task": "complis.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

user_data_fields = [
    {
        "doctype": "{doctype_1}",
        "filter_by": "{filter_by}",
        "redact_fields": ["{field_1}", "{field_2}"],
        "partial": 1,
    },
    {
        "doctype": "{doctype_2}",
        "filter_by": "{filter_by}",
        "partial": 1,
    },
    {
        "doctype": "{doctype_3}",
        "strict": False,
    },
    {
        "doctype": "{doctype_4}"
    }
]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# "complis.auth.validate"
# ]
