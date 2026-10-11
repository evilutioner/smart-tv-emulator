from __future__ import annotations

import struct
import unittest

from tests.support import mdns_profile
from tvemu.platforms.common import mdns


class MDNSTests(unittest.TestCase):
    """The shared mDNS codec, tested against a synthetic device.

    `common/mdns.py` is shared machinery, so its encoding must stay covered in a build
    whose platforms happen not to advertise over mDNS at all. The fixture keeps the case
    that matters: an instance name containing a dot, which is still one label.
    """

    HOST = "203.0.113.7"

    def setUp(self):
        self.profile = mdns_profile()

    def query(self, name, qtype=mdns.PTR, qclass=mdns.IN, query_id=7):
        return (mdns.HEADER.pack(query_id, 0, 1, 0, 0, 0) + mdns.encode_name(name)
                + struct.pack("!HH", qtype, qclass))

    def test_instance_with_dot_is_one_label(self):
        encoded = mdns.encode_name((self.profile.mdns_instance,) + self.profile.mdns_service_type)
        self.assertEqual(encoded[0], len(self.profile.mdns_instance))
        name, end = mdns.decode_name(encoded, 0)
        self.assertEqual(name[0], self.profile.mdns_instance)
        self.assertEqual(end, len(encoded))

    def test_service_response_and_qu_destination(self):
        result = mdns.responses_for(self.query(self.profile.mdns_service_type), self.profile,
                                    self.HOST)
        self.assertEqual(len(result), 1)
        packet, unicast = result[0]
        self.assertFalse(unicast)
        self.assertEqual(mdns.HEADER.unpack_from(packet)[:2], (7, 0x8400))
        self.assertIn(struct.pack("!H", 0x8001), packet)
        result = mdns.responses_for(
            self.query(self.profile.mdns_service_type, qclass=0x8001), self.profile,
            self.HOST)
        self.assertTrue(result[0][1])

    def test_legacy_unicast_uses_ttl_ten_and_enumeration_is_answered(self):
        result = mdns.responses_for(self.query(mdns.ENUMERATION), self.profile,
                                    self.HOST, source_port=12345)
        self.assertTrue(result[0][1])
        self.assertIn(struct.pack("!I", 10), result[0][0])

    def test_bad_pointers_are_rejected(self):
        with self.assertRaises(ValueError):
            mdns.decode_name(b"\xc0\x02\x00", 0)
        with self.assertRaises(ValueError):
            mdns.decode_name(b"\xc0\x00", 0)

    def test_goodbye_has_zero_ttl(self):
        packet = mdns.announcement(self.profile, self.HOST, 0)
        self.assertNotIn(struct.pack("!I", 4500), packet)
        self.assertNotIn(struct.pack("!I", 120), packet)


if __name__ == "__main__":
    unittest.main()
