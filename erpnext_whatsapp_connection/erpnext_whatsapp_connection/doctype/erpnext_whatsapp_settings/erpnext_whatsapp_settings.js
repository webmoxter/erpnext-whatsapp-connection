function render_status(frm, status) {
  const field = frm.get_field("qr_display");
  field.$wrapper.empty();
  if (status.qr_data_url) {
    $("<div class='erpnext-whatsapp-qr'></div>")
      .append($("<p></p>").text(__("Scan this temporary QR in WhatsApp > Linked devices.")))
      .append($("<img>", { src: status.qr_data_url, alt: __("Temporary WhatsApp pairing QR"), width: 320 }))
      .appendTo(field.$wrapper);
  } else if (status.connected) {
    field.$wrapper.append($("<div class='alert alert-success'></div>").text(__("WhatsApp is connected.")));
  }
}

function refresh_status(frm) {
  return frappe.call({ method: "erpnext_whatsapp_connection.settings_api.get_status" })
    .then((response) => render_status(frm, response.message || {}));
}

frappe.ui.form.on("ERPNext WhatsApp Settings", {
  refresh(frm) {
    if (frappe.model.can_write(frm.doctype)) {
      frm.add_custom_button(__("Configure Company Group"), () => {
        if (frm.doc.provider !== "Linked Device") {
          frappe.msgprint(__("Group copies require Linked Device transport."));
          return;
        }
        let groups = [];
        const dialog = new frappe.ui.Dialog({
          title: __("Company Group Copy"),
          fields: [
            {fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company"), reqd: 1},
            {fieldname: "load_groups", fieldtype: "Button", label: __("Load Joined Groups"), click: async () => {
              const company = dialog.get_value("company");
              if (!company) { frappe.msgprint(__("Select a company first.")); return; }
              const response = await frappe.call({method: "erpnext_whatsapp_connection.company_groups.list_groups", args: {company}});
              groups = response.message || [];
              dialog.set_df_property("group", "options", groups);
              dialog.set_value("group", "");
            }},
            {fieldname: "group", fieldtype: "Select", label: __("Group"), reqd: 1, options: []},
            {fieldname: "enabled", fieldtype: "Check", label: __("Enable Group CC"), default: 0},
          ],
          primary_action_label: __("Add / Update"),
          primary_action(values) {
            const selected = groups.find(row => row.value === values.group);
            if (!selected) { frappe.msgprint(__("Load and select a joined group.")); return; }
            const existing = (frm.doc.company_groups || []).find(row => row.company === values.company);
            const row = existing || frm.add_child("company_groups");
            Object.assign(row, {company: values.company, enabled: values.enabled || 0,
              group_id: selected.value, group_name: selected.label});
            frm.dirty(); frm.refresh_field("company_groups"); dialog.hide();
          },
        });
        dialog.show();
      });
    }
    frm.add_custom_button(__("Connect / Show QR"), async () => {
      await frm.save();
      const response = await frappe.call({
        method: "erpnext_whatsapp_connection.settings_api.connect",
        type: "POST",
        freeze: true,
      });
      render_status(frm, response.message || {});
    });
    frm.add_custom_button(__("Refresh Status"), () => refresh_status(frm));
    frm.add_custom_button(__("Delivery History"), () => {
      frappe.set_route("List", "ERPNext WhatsApp Delivery History");
    });
    frm.add_custom_button(__("Message Templates"), () => {
      frappe.set_route("List", "ERPNext WhatsApp Message Template");
    });
    frm.add_custom_button(__("Disconnect and Remove Authentication"), () => {
      frappe.confirm(
        __("This removes the site's linked-device or API authentication. Continue?"),
        async () => {
          await frappe.call({
            method: "erpnext_whatsapp_connection.settings_api.disconnect_and_remove_authentication",
            type: "POST",
            freeze: true,
          });
          await refresh_status(frm);
        },
      );
    });
    refresh_status(frm);
  },
});
