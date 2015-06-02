from _Framework.Capabilities import CONTROLLER_ID_KEY, PORTS_KEY, NOTES_CC, SCRIPT, REMOTE, controller_id, inport, outport
from BehringerFCB1010 import BehringerFCB1010

def create_instance(c_instance):
    return BehringerFCB1010(c_instance)


def get_capabilities():
    # No idea what to change vendor and product IDs to - they're not the MIDI vendor names
    return {CONTROLLER_ID_KEY: controller_id(vendor_id=2536, product_ids=[40], model_name='FCB1010'),
     PORTS_KEY: [inport(props=[NOTES_CC, SCRIPT, REMOTE]), outport(props=[])]}