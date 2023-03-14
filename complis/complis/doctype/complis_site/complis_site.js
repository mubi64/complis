// Copyright (c) 2023, Sowaan and contributors
// For license information, please see license.txt

frappe.ui.form.on('Complis Site', {
	// refresh: function(frm) {

	// }
	sync_invoices: function (frm) {
		frappe.call({
			method: "complis.complis.doctype.complis_site.complis_site.sync_invoices",
			// args: {
			// 	"doc": frm.doc
			// },
			callback: function (r) {
				if (!r.exc) {
					// frm.set_value('access_token', r.message)
					// frm.save();
				}
			},
			freeze: true,
			freeze_message: __('Syncing data from Complis...')
		});
	}
});

cur_frm.set_query("receivable_account", function (doc) {
	return {
		filters: {
			'account_type': 'Receivable',
			'is_group': 0,
		}
	}
});
