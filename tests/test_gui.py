"""Exercise the preview's input and media paths without creating a Tk window."""
import os
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from xml.etree import ElementTree

from helpers import FLASH, ROOT, tiny_image
from lab404 import emulator


def write_padconf(path):
    header = b'RFPD' + struct.pack('>I', 0xA0) + struct.pack('<I', 3) + struct.pack('>I', 0x7A80)
    path.write_bytes(header.ljust(0xCB20, b'\0'))


def write_wav(path):
    pcm = b'\0\0'
    fmt = struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, 1, 48000, 96000, 2, 16)
    data = struct.pack('<4sI', b'data', len(pcm)) + pcm
    riff = struct.pack('<4sI4s', b'RIFF', 4 + len(fmt) + len(data), b'WAVE')
    path.write_bytes(riff + fmt + data)


def bootable_tiny_image():
    image = bytearray(tiny_image().ljust(0x800, b'\0'))
    struct.pack_into('<II', image, 0x6EC, 0x20080000, (FLASH + 0x100) | 1)
    return bytes(image)


class Input(unittest.TestCase):
    def setUp(self):
        from lab404.gui import ControlState

        self.events = []
        self.state = ControlState(lambda name, down: self.events.append((name, down)))

    def test_physical_sources_share_one_contact(self):
        for source in ('left', 'right'):
            self.state.press('SHIFT', source)
        self.state.release('SHIFT', 'left')
        self.assertEqual(self.events, [('SHIFT', True)])
        self.state.release('SHIFT', 'right')
        self.assertEqual(self.events[-1], ('SHIFT', False))

    def test_right_click_latches_any_button_and_left_click_releases_it(self):
        self.state.toggle_latch('PAD5')
        self.assertEqual(self.state.latched, {'PAD5': 'Lock'})
        self.state.mouse_press('PAD5')
        self.state.release('PAD5', 'mouse')
        self.assertEqual(self.events, [('PAD5', True), ('PAD5', False)])

    def test_one_shot_releases_modifiers_after_the_pad_only(self):
        self.state.mode = 'One-shot'
        for name in ('SHIFT', 'REMAIN'):
            self.state.mouse_press(name)
            self.state.release(name, 'mouse')
        self.state.press('PAD13', 'keyboard')
        self.assertEqual(set(self.state.latched), {'SHIFT', 'REMAIN'})
        self.state.release('PAD13', 'keyboard')
        self.assertEqual(self.events, [('SHIFT', True), ('REMAIN', True), ('PAD13', True),
                                      ('PAD13', False), ('SHIFT', False), ('REMAIN', False)])

    def test_one_shot_ignores_a_pad_already_down_when_armed(self):
        self.state.mode = 'One-shot'
        self.state.press('PAD1', 'keyboard')
        self.state.mouse_press('SHIFT')
        self.state.release('PAD1', 'keyboard')
        self.assertEqual(set(self.state.latched), {'SHIFT'})

    def test_lock_survives_multiple_pads_and_release_all_clears_latches(self):
        self.state.mode = 'Lock'
        self.state.mouse_press('REMAIN')
        for pad in ('PAD1', 'PAD2'):
            self.state.mouse_press(pad)
            self.state.release(pad, 'mouse')
        self.state.press('HOLD', 'h')
        self.state.release_all()
        self.assertEqual(self.state.active, {'HOLD'})
        self.assertEqual(self.events[-1], ('REMAIN', False))

    def test_timed_hold_releases_at_3_point_2_seconds(self):
        self.state.timed_hold('MARK', 10.0)
        self.state.expire(13.199)
        self.assertEqual(self.events, [('MARK', True)])
        self.state.expire(13.2)
        self.assertEqual(self.events[-1], ('MARK', False))

    def test_repeat_release_pair_keeps_contact_until_real_release(self):
        from lab404.gui import KeyboardState

        key = KeyboardState(self.state, lambda step: None, lambda: None, lambda: None)
        key.press(43, 'h', 10)
        key.defer_release(43, 15)
        key.press(43, 'h', 15)
        key.press(43, 'h', 16)
        key.flush()
        self.assertEqual(self.events, [('HOLD', True)])
        key.defer_release(43, 20)
        key.flush()
        self.assertEqual(self.events[-1], ('HOLD', False))

    def test_russian_keysyms_press_the_same_x11_pads_and_shortcuts(self):
        from lab404.gui import KeyboardState, X11_KEYS

        key = KeyboardState(self.state, lambda step: None, lambda: None, lambda: None, positions=X11_KEYS)
        for code, symbol, control in [(24, 'Cyrillic_shorti', 'PAD5'),
                                      (38, 'Cyrillic_ef', 'PAD9'),
                                      (52, 'Cyrillic_ya', 'PAD13'),
                                      (43, 'Cyrillic_er', 'HOLD')]:
            key.press(code, symbol, 10)
            key.defer_release(code, 20)
            key.flush()
            self.assertEqual(self.events[-2:], [(control, True), (control, False)])

    def test_keymap_and_panel_cover_the_emulator_controls(self):
        from lab404.gui import KEYMAP, MODIFIERS, PAD_KEYS, PANEL_LAYOUT

        names = {*emulator.KEYS, 'SHIFT', 'SUB PAD', *(f'PAD{n}' for n in emulator.PADS)}
        self.assertEqual(''.join(PAD_KEYS), '1234qwerasdfzxcv')
        for n, key in enumerate(PAD_KEYS, 1):
            self.assertEqual(KEYMAP[key], f'PAD{n}')
            self.assertNotIn(KEYMAP[key], MODIFIERS)
        self.assertLessEqual(set(KEYMAP.values()) | MODIFIERS, names)
        self.assertEqual(set(PANEL_LAYOUT), names | {*emulator.KNOBS, 'VOLUME', 'OLED'})
        svg = ElementTree.parse(ROOT/'docs/panel-layout.svg')
        self.assertEqual({item.attrib['data-control'] for item in svg.iter() if 'data-control' in item.attrib},
                         set(PANEL_LAYOUT))


class Session(unittest.TestCase):
    def test_reopens_the_last_firmware_and_project_from_a_different_directory(self):
        from lab404.gui import _remember_session, _startup_sources

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app1 = root/'APP1.bin'
            project = root/'Проект'
            state = root/'settings/session.json'
            app1.touch()
            project.mkdir()
            _remember_session(state, app1, project)
            self.assertEqual(_startup_sources(state, None, None), (app1, project))
            replacement = root/'New APP1.bin'
            replacement.touch()
            self.assertEqual(_startup_sources(state, str(replacement), None), (replacement, project))
            other = root/'Other'
            self.assertEqual(_startup_sources(state, None, str(other)), (app1, other))
            self.assertEqual(_startup_sources(state, str(replacement), str(other)), (replacement, other))

    def test_unplugged_project_is_preserved_for_the_next_launch(self):
        from lab404.gui import _remember_session, _startup_sources

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, app1, project = root/'session.json', root/'APP1.bin', root/'Card'
            app1.touch()
            project.mkdir()
            _remember_session(state, app1, project)
            project.rmdir()
            self.assertEqual(_startup_sources(state, None, None), (app1, None))
            _remember_session(state, app1, None)
            project.mkdir()
            self.assertEqual(_startup_sources(state, None, None), (app1, project))

    def test_invalid_saved_state_allows_the_window_to_start_blank(self):
        from lab404.gui import _startup_sources

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)/'session.json'
            state.write_text('{interrupted', encoding='utf-8')
            self.assertEqual(_startup_sources(state, None, None), (None, None))


class EmulatorPreview(unittest.TestCase):
    def test_gui_rejects_a_scatter_container_without_firmware_vectors(self):
        from lab404.gui import _boot

        with tempfile.TemporaryDirectory() as directory:
            app1 = Path(directory)/'SP404MKII_APP1.bin'
            app1.write_bytes(tiny_image())
            with patch('lab404.gui.find_qemu', return_value=Path(directory)/'missing-qemu'):
                with self.assertRaisesRegex(ValueError, 'APP1.*boot vectors'):
                    _boot(app1, None, None, None)

    def test_gui_validates_app1_headers_and_vectors(self):
        from lab404.gui import _load_app1

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root/'SP404MKII_APP1.bin'
            valid.write_bytes(bootable_tiny_image())
            image, info = _load_app1(valid)
            self.assertEqual(info['status'], 'unknown')
            self.assertEqual(len(image), 0x800)

            bad_stack = bytearray(bootable_tiny_image())
            struct.pack_into('<I', bad_stack, 0x6EC, 0x10000000)
            (root/'bad-stack.bin').write_bytes(bad_stack)
            with self.assertRaisesRegex(ValueError, 'initial stack'):
                _load_app1(root/'bad-stack.bin')

            bad_reset = bytearray(bootable_tiny_image())
            struct.pack_into('<I', bad_reset, 0x6F0, FLASH + 0x100)
            (root/'bad-reset.bin').write_bytes(bad_reset)
            with self.assertRaisesRegex(ValueError, 'reset address'):
                _load_app1(root/'bad-reset.bin')

            (root/'non-app1.bin').write_bytes(b'\0' * 0x1000)
            with self.assertRaisesRegex(ValueError, 'initial stack|APP1'):
                _load_app1(root/'non-app1.bin')

    def test_project_folder_rejects_symlinks_inside_padconf_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root/'PROJECT_01'
            samples = project/'SMPL'
            samples.mkdir(parents=True)
            write_padconf(project/'PADCONF.BIN')
            target = root/'outside.txt'
            target.write_text('x', encoding='utf-8')
            try:
                (samples/'link.smp').symlink_to(target)
            except OSError:
                self.skipTest('symbolic links unavailable')
            with self.assertRaisesRegex(ValueError, 'symbolic links'):
                emulator.check_project_source(project, root, cancel=emulator.threading.Event())

    def test_project_folder_rejects_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'unrelated.txt').write_text('arbitrary file', encoding='utf-8')
            with patch.object(emulator, '_run_fatimg') as run:
                with self.assertRaisesRegex(ValueError, 'SP-404MKII project or WAV'):
                    emulator.prepare_project_media(root, root, fatimg='fatimg')
            run.assert_not_called()

    def test_project_folder_rejects_invalid_padconf_or_wav(self):
        for filename in ('PADCONF.BIN', 'renamed.wav'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root/filename).write_bytes(b'not valid data')
                with patch.object(emulator, '_run_fatimg') as run:
                    with self.assertRaisesRegex(ValueError, filename):
                        emulator.prepare_project_media(root, root, fatimg='fatimg')
                run.assert_not_called()

    def test_invalid_disk_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root/'unrelated.img'
            image.write_bytes(b'not a disk')
            with self.assertRaisesRegex(ValueError, 'project image'):
                emulator.prepare_project_media(image, root, fatimg='fatimg')

    def test_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tcp = emulator.select_transport(root, windows=True)
            self.assertEqual(tcp.family, socket.AF_INET)
            self.assertEqual(tcp.link[0], '127.0.0.1')
            self.assertEqual(tcp.monitor[0], '127.0.0.1')
            self.assertNotEqual(tcp.link, tcp.monitor)
            self.assertIn('server=on,wait=on', tcp.chardev)
            self.assertTrue(tcp.monitor_arg.startswith('tcp:127.0.0.1:'))
            if hasattr(socket, 'AF_UNIX'):
                unix = emulator.select_transport(root, windows=False)
                self.assertEqual(unix.family, socket.AF_UNIX)
                self.assertEqual(unix.link, str(root/'link.sock'))
                self.assertTrue(unix.monitor_arg.startswith('unix:'))

    @unittest.skipUnless(hasattr(socket, 'AF_UNIX'), 'Unix sockets unavailable')
    def test_transport_preserves_commas_in_unix_socket_paths(self):
        root = Path('/tmp/work,copy')
        transport = emulator.select_transport(root, windows=False)
        self.assertEqual(transport.link, str(root/'link.sock'))
        self.assertEqual(transport.monitor, str(root/'monitor.sock'))
        escaped = str(root).replace(',', ',,')
        self.assertIn(f'path={escaped}{os.sep}link.sock,server=on', transport.chardev)
        self.assertEqual(transport.monitor_arg, f'unix:{escaped}{os.sep}monitor.sock,server,nowait')

    def test_image_is_passed_directly_and_card_images_use_the_sd_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            internal, card, wav_card = root/'project-drive.img', root/'card.img', root/'wav-card.img'
            exfat_boot = bytearray(512)
            exfat_boot[3:11] = b'EXFAT   '
            exfat_boot[-2:] = b'\x55\xaa'
            internal.write_bytes(exfat_boot)
            fat_boot = bytearray(512)
            fat_boot[82:90] = b'FAT32   '
            fat_boot[-2:] = b'\x55\xaa'
            card.write_bytes(fat_boot)
            wav_card.write_bytes(fat_boot)

            def fake_fatimg(args, cancel, *, capture=False):
                cmd, image, target = args[1], Path(args[2]), args[3]
                if cmd == 'ls':
                    if image == internal and target == '/ROLAND/SP-404MKII':
                        return '2026-11-09 19:34        <DIR>  PROJECT_01\n'
                    if image == internal and target == '/ROLAND/SP-404MKII/PROJECT_01':
                        return '2026-11-09 19:34        52000  PADCONF.BIN\n'
                    if image == card and target == '/IMPORT':
                        return '2026-11-09 19:34        <DIR>  P6_PROJECT_06\n'
                    if image == card and target == '/IMPORT/P6_PROJECT_06':
                        return '2026-11-09 19:34        52000  PADCONF.BIN\n'
                    if image == wav_card and target == '/IMPORT':
                        return '2026-11-09 19:34           46  kick.wav\n'
                    raise RuntimeError('no such path')
                if cmd == 'get':
                    dest = Path(args[4])
                    if target.endswith('PADCONF.BIN'):
                        write_padconf(dest/'PADCONF.BIN')
                    else:
                        write_wav(dest/'kick.wav')
                    return ''
                raise AssertionError(args)

            with patch.object(emulator, '_run_fatimg', side_effect=fake_fatimg):
                self.assertEqual(emulator.prepare_project_media(internal, root, fatimg='fatimg').drive, internal)
                self.assertEqual(emulator.prepare_project_media(card, root, fatimg='fatimg').sd_card, card)
                self.assertEqual(emulator.prepare_project_media(wav_card, root, fatimg='fatimg').sd_card, wav_card)
            self.assertEqual(internal.read_bytes(), exfat_boot)

    def test_empty_project_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            internal = root/'blank.img'
            boot = bytearray(512)
            boot[3:11] = b'EXFAT   '
            boot[-2:] = b'\x55\xaa'
            internal.write_bytes(boot)
            with patch.object(emulator, '_run_fatimg', side_effect=RuntimeError('no such path')):
                with self.assertRaisesRegex(ValueError, 'no SP-404MKII project'):
                    emulator.prepare_project_media(internal, root, fatimg='fatimg')

    def test_folder_is_packed_in_import_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            samples = root/'samples'
            samples.mkdir()
            wav = samples/'kick.wav'
            write_wav(wav)
            (samples/'firmware.bin').write_bytes(b'not a sample')
            with patch.object(emulator, '_run_fatimg') as run:
                media = emulator.prepare_project_media(samples, root, fatimg='fatimg')
            self.assertEqual(media.sd_card, root/'project.img')
            self.assertEqual(run.call_args_list[0].args[0][1:3], ['create', str(media.sd_card)])
            self.assertEqual(run.call_args_list[-1].args[0], ['fatimg', 'add', str(media.sd_card), str(wav), '/IMPORT'])
            self.assertEqual(run.call_count, 2)

    def test_named_export_boots_from_the_first_internal_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            project = root/'P7_PROJECT_07'
            samples = project/'SMPL'
            samples.mkdir(parents=True)
            config = project/'PADCONF.BIN'
            write_padconf(config)
            (samples/'BANK1-01.SMP').write_bytes(b'RFWV')
            with patch.object(emulator, '_run_fatimg') as run:
                media = emulator.prepare_project_media(project, root, fatimg='fatimg')
            self.assertEqual(media.drive, root/'project.img')
            self.assertIsNone(media.sd_card)
            calls = [call.args[0] for call in run.call_args_list]
            slot = '/ROLAND/SP-404MKII/PROJECT_01'
            self.assertEqual(calls[0][4:6], ['exfat', 'bare'])
            self.assertIn(slot[1:], calls[0])
            for entry in (config, samples):
                self.assertIn(['fatimg', 'add', str(media.drive), str(entry), slot], calls)
            self.assertEqual(config.stat().st_size, 0xCB20)

    def test_app_and_card_exports_are_available_in_the_import_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            layouts = (('App', 'Roland', 'SP-404MKII'), ('Export', 'Project'))
            for layout in layouts:
                with self.subTest(layout=layout):
                    project = root.joinpath(*layout, 'PROJECT_01')
                    project.mkdir(parents=True)
                    write_padconf(project/'PADCONF.BIN')
                    with patch.object(emulator, '_run_fatimg') as run:
                        emulator.prepare_project_media(root/layout[0], root, fatimg='fatimg')
                    self.assertIn(['fatimg', 'add', str(root/'project.img'), str(project), '/IMPORT'],
                                  [call.args[0] for call in run.call_args_list])

    def test_missing_fatimg_reports_setup_hint(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(emulator, 'find_fatimg', return_value=None):
            write_wav(Path(directory)/'kick.wav')
            with self.assertRaisesRegex(RuntimeError, r'fatimg'):
                emulator.prepare_project_media(Path(directory), Path(directory))

    def test_led_packets_update_brightness_and_ignore_midi(self):
        unit = emulator.Emulator(b'')
        unit._read_leds(bytes((1, 0, 0, 100, 0x11, 7, 0, 200, 4, 9, 0, 255)), 10)
        self.assertEqual(unit.leds, {0: (100, 7, 200)})
        self.assertEqual(emulator.led_level(unit.leds[0], 0), 100)
        self.assertEqual(emulator.led_level(unit.leds[0], 1/3), 200)
        self.assertEqual(emulator.led_level((255, 6, 180), 0.4), 0)

    def test_ctrl_clockwise_sends_maximum_and_counterclockwise_minimum(self):
        unit = emulator.Emulator(b'')
        writer, reader = socket.socketpair()
        with writer, reader, reader.makefile('rb') as packets:
            unit.sock = writer
            for name, mux in (('CTRL 1', 1), ('CTRL2', 2), ('CTRL3', 3)):
                for position, adc in ((0, 4095), (2048, 2047), (4095, 0)):
                    with self.subTest(name=name, position=position):
                        unit.set_knob(name, position)
                        payload = struct.unpack('<BBHBBBH', packets.read(9))
                        self.assertEqual(payload, (0x82, 0, 5, 0, 6, mux, adc))

    def test_native_audio_batches_wire_packets_without_losing_samples(self):
        unit = emulator.Emulator(b'', audio_sink=emulator.NativeAudioPlayer())
        packets = [bytes([number])*256 for number in range(8)]
        for packet in packets[:-1]:
            unit._deliver_audio(packet)
        self.assertTrue(unit.audio_queue.empty())
        unit._deliver_audio(packets[-1])
        self.assertEqual(unit.audio_queue.get_nowait(), b''.join(packets))

    def test_audio_rate_correction_keeps_stereo_channels_and_endpoints(self):
        stereo = struct.pack('<8h', 0, 0, 100, -100, 200, -200, 300, -300)
        faster = struct.unpack('<6h', emulator._retime_pcm(stereo, -1))
        slower = struct.unpack('<10h', emulator._retime_pcm(stereo, 1))
        self.assertEqual(faster, (0, 0, 150, -150, 300, -300))
        self.assertEqual(slower, (0, 0, 75, -75, 150, -150, 225, -225, 300, -300))

    def test_audio_primes_backend_before_the_first_write(self):
        player = emulator.NativeAudioPlayer()
        backend, factory = Mock(), Mock()
        factory.return_value = backend
        player._backends = iter([factory])
        block = bytes(2048)
        for _ in range(5):
            player(block)
        factory.assert_not_called()
        player(block)
        factory.assert_called_once()
        backend.write.assert_called_once_with(block*6, player._stop)
        player(block)
        self.assertEqual(backend.write.call_args.args[0], block)

    def test_audio_queue_drops_oldest_and_volume_uses_signed_pcm(self):
        unit = emulator.Emulator(b'', audio_sink=lambda pcm: None)
        for n in range(20):
            unit._queue_audio(bytes([n])*4)
        self.assertEqual(unit.audio_queue.qsize(), 16)
        self.assertEqual(unit.audio_queue.get_nowait(), b'\x04'*4)
        player = emulator.NativeAudioPlayer()
        player.volume = 50
        self.assertEqual(player.level(b'\x00\x80\xfe\x7f'), b'\x00\xc0\xff\x3f')
        player.muted = True
        self.assertEqual(player.level(b'\x00\x80\xfe\x7f'), bytes(4))

    def test_linux_uses_kde_file_dialog_with_an_app1_filter(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE:Plasma'}), \
                patch.object(emulator.shutil, 'which', side_effect=lambda name: '/' + name), \
                patch.object(emulator, '_run_picker', return_value='/tmp/Firmware.bin') as run:
            path = emulator.pick_linux_path('Load APP1 firmware', '/tmp', ('APP1 firmware', '*.bin *.BIN'))
        self.assertEqual(path, '/tmp/Firmware.bin')
        args = run.call_args.args[0]
        self.assertEqual(args[0], '/kdialog')
        self.assertIn('--getopenfilename', args)
        self.assertTrue(any('*.bin' in arg for arg in args))

    def test_linux_folder_uses_gtk_and_cancel_keeps_the_current_project(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'GNOME'}), \
                patch.object(emulator.shutil, 'which', side_effect=lambda name: '/' + name), \
                patch.object(emulator, '_run_picker', return_value=None) as run:
            self.assertIsNone(emulator.pick_linux_path('Import project folder', '/tmp'))
        args = run.call_args.args[0]
        self.assertEqual(args[0], '/zenity')
        self.assertIn('--directory', args)
        run.assert_called_once()

    def test_gui_help_needs_no_display(self):
        env = {key: value for key, value in os.environ.items() if key not in ('DISPLAY', 'WAYLAND_DISPLAY')}
        proc = subprocess.run([sys.executable, '-m', 'lab404', 'gui', '--help'], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=20, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('--project', proc.stdout)
        self.assertIn('--no-audio', proc.stdout)


if __name__ == '__main__':
    unittest.main()
