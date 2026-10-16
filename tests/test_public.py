"""No USB device is opened; private original images are not required."""
from pathlib import Path
import struct,sys,unittest
from unittest.mock import patch as mock_patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'src/u15l/device'),str(ROOT/'tests/flows')]
from u15l.common import case_path
from u15l.prepare import unpack,prepare,select_candidate
from u15l.fixed import load_fixed,validate_payload,FILENAME,PAYLOAD_SHA
from u15l_noop_package import make_noop_package
from u15l_recovery_package import make_restore_package,START,SIZE
from u15l_candidate_package import make_candidate_package
from u15l_install_flow import install,verify_image
from check_noop_flow_offline import case as noop_case

class PublicChecks(unittest.TestCase):
    def test_fixed_component_integrity_and_corruption(self):
        payload=load_fixed()
        if payload is None:self.skipTest('Source-only distribution')
        self.assertEqual(len(validate_payload(payload)),0x294fb4)
        bad=bytearray(payload);bad[-1]^=1
        for value in (bytes(bad),payload[:-1],payload+b'\x00'):
            with self.assertRaises(RuntimeError):validate_payload(value)
    def test_unknown_original_cannot_use_fixed_or_local(self):
        for method in ('auto','fixed','local'):
            with mock_patch('u15l.prepare.load_fixed') as loader:
                with self.assertRaises(RuntimeError):select_candidate(bytes(0x1000000),method)
                loader.assert_not_called()
    def test_partial_fixed_bundle_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'firmware').mkdir()
            self.assertIsNone(load_fixed(root))
            (root/'firmware'/FILENAME).write_bytes(b'broken')
            with self.assertRaises(RuntimeError):load_fixed(root)
    def test_auto_does_not_hide_corrupted_component(self):
        with mock_patch('u15l.prepare.unpack',return_value=(b'',b'')),mock_patch('u15l.prepare.load_fixed',side_effect=RuntimeError('damaged')),mock_patch('u15l.prepare.patch') as local:
            with self.assertRaises(RuntimeError):select_candidate(b'','auto')
            local.assert_not_called()
    def test_metadata_has_zero_write_entries(self):
        tim,fbf=make_noop_package()
        self.assertEqual((len(tim),len(fbf)),(1024,4096))
        self.assertEqual(struct.unpack_from('<I',tim,0x28)[0],0x5350491b)
        for at in (0x144,0x148,0x1e4,0x1f0):self.assertEqual(struct.unpack_from('<I',fbf,at)[0],0)
    def test_noop_transport_and_error_cases(self):
        for kind in ('success','wrong_image','header_nack','small_buffer','data_nack','wrong_sequence','device_error','unexpected_erase_notice','no_ready'):
            with self.subTest(kind=kind):noop_case(kind)
    def test_invalid_case_path(self):
        for name in ('../other','a/b','','x'*65,'你好'):
            with self.assertRaises(ValueError):case_path(name)
    def test_wrong_board_stops_before_reading_data(self):
        with self.assertRaises(RuntimeError):prepare('no-device','other','ASR1803S','U15L-MT02B01V15-L01')
    def test_unknown_firmware_rejected(self):
        for data in (bytes(4096),bytes(0x1000000)):
            with self.assertRaises(RuntimeError):unpack(data)
    def test_unrendered_templates_cannot_write(self):
        with self.assertRaises(RuntimeError):make_restore_package(bytes(SIZE))
        with self.assertRaises(RuntimeError):make_candidate_package(bytes(SIZE),bytes(SIZE))
    def test_restore_failure_prevents_candidate(self):
        original=bytes(0x1000000);candidate=b'\x42'*SIZE;writes=[]
        def read(number,label):
            data=bytearray(original)
            if number==3:data[START]^=1
            return bytes(data)
        def write(number,kind,payload):writes.append(kind)
        with self.assertRaises(RuntimeError):install(original,candidate,read,write,lambda *_:None)
        self.assertEqual(writes,['original'])
    def test_protected_changes_rejected(self):
        original=bytes(0x1000000);other=bytearray(original);other[0x6000]=1
        with self.assertRaises(RuntimeError):verify_image(bytes(other),original,bytes(SIZE))
    def test_runtime_changes_preserved(self):
        original=bytes(0x1000000);other=bytearray(original);other[0xa00000]=1
        verify_image(bytes(other),original,bytes(SIZE))
    def test_read_policy_cannot_download(self):
        from restore_u15l_original import READ_POLICY
        self.assertFalse({0x20,0x22,0x26,0x27,0x2a}&{x[0] for x in READ_POLICY})
        for request in READ_POLICY:
            if request[0]==0x32:self.assertEqual(request[9],27)

if __name__=='__main__':unittest.main()
