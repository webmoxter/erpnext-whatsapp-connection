window.erpnext_whatsapp_connection = window.erpnext_whatsapp_connection || {};

(() => {
  const api = window.erpnext_whatsapp_connection;
  const defaultReports = new Set([
    "Accounts Receivable",
    "Accounts Receivable Summary",
    "Customer Ledger Summary",
    "General Ledger",
  ]);

  function apiUrl(method, args) {
    const query = new URLSearchParams();
    Object.entries(args || {}).forEach(([key, value]) => {
      query.set(key, typeof value === "string" ? value : JSON.stringify(value));
    });
    return `/api/method/erpnext_whatsapp_connection.api.${method}?${query.toString()}`;
  }

  function selectedTemplate(context, value) {
    return context.templates.find((row) => row.name === value)
      || context.templates.find((row) => row.is_default)
      || context.templates[0];
  }

  function showDialog({ context, kind, source }) {
    if (!context.recipients.length) {
      frappe.msgprint(__("No valid international WhatsApp number is linked to this customer."));
      return;
    }
    const defaultTemplate = selectedTemplate(context, "");
    const fields = [{
      fieldname: "recipient",
      fieldtype: "Select",
      label: __("Customer WhatsApp Number"),
      options: context.recipients.map((row) => row.value),
      reqd: 1,
    }];
    if (kind === "document") {
      fields.push({
        fieldname: "print_format",
        fieldtype: "Select",
        label: __("Print Format"),
        options: context.print_formats,
        reqd: 1,
      });
    }
    fields.push(
      {
        fieldname: "message_template",
        fieldtype: "Select",
        label: __("Message Template"),
        options: context.templates.map((row) => ({ label: row.label, value: row.name })),
        default: defaultTemplate?.name || "",
      },
      {
        fieldname: "message",
        fieldtype: "Small Text",
        label: __("Message"),
        default: defaultTemplate?.message || "",
        reqd: 1,
      },
      {
        fieldname: "recipient_help",
        fieldtype: "HTML",
        options: `<p class="text-muted small">${__("Numbers are loaded only from the selected customer's permitted Customer, Contact, and Address records.")}</p>`,
      },
    );
    const dialog = new frappe.ui.Dialog({
      title: __("Send by WhatsApp"),
      fields,
      primary_action_label: __("Send"),
      async primary_action(values) {
        const args = {
          recipient: values.recipient,
          message: values.message,
          message_template: values.message_template || "",
          ...source,
        };
        if (kind === "document") args.print_format = values.print_format;
        const method = kind === "document" ? "queue_document" : "queue_report";
        const response = await frappe.call({
          method: `erpnext_whatsapp_connection.api.${method}`,
          type: "POST",
          args,
          freeze: true,
          freeze_message: __("Creating a private PDF snapshot and queueing delivery…"),
        });
        dialog.hide();
        const name = response.message?.name;
        frappe.show_alert({ message: __("WhatsApp delivery queued"), indicator: "green" });
        if (name) frappe.set_route("Form", "ERPNext WhatsApp Delivery History", name);
      },
    });
    dialog.fields_dict.message_template.df.onchange = () => {
      const template = selectedTemplate(context, dialog.get_value("message_template"));
      if (template) dialog.set_value("message", template.message);
    };
    dialog.set_secondary_action_label(__("Preview PDF"));
    dialog.set_secondary_action(() => {
      const values = dialog.get_values(true);
      const method = kind === "document" ? "preview_document_pdf" : "preview_report_pdf";
      const args = { ...source };
      if (kind === "document") args.print_format = values.print_format;
      window.open(apiUrl(method, args), "_blank", "noopener,noreferrer");
    });
    dialog.show();
  }

  api.attach_document_button = function attachDocumentButton(frm) {
    if (!frm || frm.is_new() || frm.doc.__islocal) return;
    frm.add_custom_button(__("Send by WhatsApp"), async () => {
      const response = await frappe.call({
        method: "erpnext_whatsapp_connection.api.prepare_document",
        args: { doctype: frm.doctype, name: frm.docname },
        freeze: true,
      });
      const context = response.message;
      showDialog({
        context,
        kind: "document",
        source: {
          doctype: frm.doctype,
          name: frm.docname,
          source_modified: context.source_modified,
        },
      });
    });
  };

  api.attach_report_button = function attachReportButton(reportName, report) {
    if (!report?.page || report.page.__erpnext_whatsapp_button) return;
    report.page.__erpnext_whatsapp_button = true;
    report.page.add_inner_button(__("Send by WhatsApp"), async () => {
      const filters = report.get_filter_values();
      const response = await frappe.call({
        method: "erpnext_whatsapp_connection.api.prepare_report",
        args: { report_name: reportName, filters },
        freeze: true,
      });
      showDialog({
        context: response.message,
        kind: "report",
        source: { report_name: reportName, filters: JSON.stringify(filters) },
      });
    });
  };

  function attachCurrentReport() {
    const route = frappe.get_route();
    if (route[0] !== "query-report" || !defaultReports.has(route[1])) return;
    window.setTimeout(() => api.attach_report_button(route[1], frappe.query_report), 250);
  }

  $(document).on("page-change", attachCurrentReport);
  frappe.router.on("change", attachCurrentReport);
})();
