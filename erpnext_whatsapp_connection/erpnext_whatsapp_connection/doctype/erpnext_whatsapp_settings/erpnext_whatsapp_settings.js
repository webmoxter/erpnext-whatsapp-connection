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
