frappe.ui.form.on("ERPNext WhatsApp Automation Request", {
  refresh(frm) {
    if (frm.is_new() || frm.doc.status !== "Pending Approval") return;
    if (!frappe.user.has_role("ERPNext WhatsApp Manager") && !frappe.user.has_role("System Manager")) return;
    const call = (method) => frappe.call({
      method: "erpnext_whatsapp_connection.automation." + method,
      args: { request_name: frm.doc.name },
      freeze: true,
      callback(r) {
        if (r.message) frm.reload_doc();
      },
    });
    frm.add_custom_button(__("Approve and queue"), () => {
      frappe.confirm(__("Queue this notification after checking customer consent and document access?"),
        () => call("approve_request"));
    }, __("WhatsApp Automation"));
    frm.add_custom_button(__("Reject"), () => {
      frappe.confirm(__("Reject this automatic WhatsApp notification?"),
        () => call("reject_request"));
    }, __("WhatsApp Automation"));
  },
});
