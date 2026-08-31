frappe.ui.form.on(cur_frm.doctype, {
  refresh(frm) {
    erpnext_whatsapp_connection.attach_document_button(frm);
  },
});
