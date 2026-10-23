import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

test('real composer script shows configured CC notice without accepting a caller group destination', async () => {
  const source = fs.readFileSync(new URL('../../erpnext_whatsapp_connection/public/js/send_by_whatsapp.js', import.meta.url), 'utf8');
  for (const enabled of [false, true]) {
    let button, dialog;
    const requests = [];
    const frappe = {
      get_route: () => null, router: { on() {} }, set_route() {}, show_alert() {},
      call: async args => {
        requests.push(args);
        return { message: args.method.endsWith('prepare_document') ? {
          recipients: [{value: '+12025550187'}], print_formats: ['Standard'], templates: [],
          source_modified: 'Synthetic original version', company_group_copy: enabled,
        } : { name: 'Synthetic delivery' } };
      },
      ui: { Dialog: class {
        constructor(options) {
          dialog = this;this.options = options;this.fields_dict = { message_template: { df: {} } };
        }
        set_secondary_action_label() {} set_secondary_action() {} show() {} hide() {}
      } },
    };
    const window = { setTimeout() {} };
    vm.runInNewContext(source, {window,frappe,document:{},$:()=>({on(){}}),
      __: value=>value,URLSearchParams,JSON,Set});
    window.erpnext_whatsapp_connection.attach_document_button({ is_new:()=>false, doc:{},
      doctype:'Synthetic Invoice', docname:'Synthetic original', add_custom_button:(_label,fn)=>{button=fn;} });
    await button();
    assert.equal(dialog.options.fields.some(field=>field.fieldname==='group_copy_notice'),enabled);
    await dialog.options.primary_action({recipient:'+12025550187',message:'Synthetic copy',
      print_format:'Standard',group_id:'forged-group'});
    assert.equal('group_id' in requests[1].args,false);
    assert.equal('company' in requests[1].args,false);
    assert.equal(requests[1].args.source_modified,'Synthetic original version');
  }
});
