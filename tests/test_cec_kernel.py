"""Tests de la lectura por el API del kernel, con un adaptador simulado."""
import array
import errno
import struct

import pytest

import cec_kernel as ck


class FakeAdapter(object):
    """Simula /dev/cecN respondiendo a las ioctl que usa CecKernel."""

    def __init__(self, phys=0x1000, log_addr=1, tx_status=0x01, rx_status=0x01,
                 reply=b"\x01\x90\x00", busy=False, missing=False):
        self.phys, self.log_addr = phys, log_addr
        self.tx_status, self.rx_status, self.reply = tx_status, rx_status, reply
        self.busy, self.missing = busy, missing
        self.mode = None
        self.sent = None
        self.reply_opcode = None
        self.closed = 0

    def open(self, path, flags):
        if self.missing:
            raise OSError(errno.ENOENT, "no existe")
        return 7

    def close(self, fd):
        self.closed += 1

    def ioctl(self, fd, request, arg, mutate=False):
        if request == ck.CEC_S_MODE:
            if self.busy:
                raise OSError(errno.EBUSY, "ocupado")
            self.mode = struct.unpack("I", arg)[0]
        elif request == ck.CEC_ADAP_G_PHYS_ADDR:
            arg[0] = self.phys
        elif request == ck.CEC_ADAP_G_LOG_ADDRS:
            arg[0] = self.log_addr
        elif request == ck.CEC_TRANSMIT:
            raw = bytearray(bytes(arg))
            length = struct.unpack_from("I", raw, 16)[0]
            self.sent = bytes(raw[32:32 + length])
            self.reply_opcode = raw[48]
            struct.pack_into("I", raw, 16, len(self.reply))
            raw[32:48] = self.reply.ljust(16, b"\0")
            raw[49], raw[50] = self.rx_status, self.tx_status
            arg[:] = array.array("B", bytes(raw))
        else:
            raise AssertionError("ioctl inesperada %#x" % request)
        return 0


def kernel(adapter, exists=lambda p: True):
    return ck.CecKernel(ioctl=adapter.ioctl, open_=adapter.open,
                        close=adapter.close, exists=exists)


def test_numeros_de_ioctl_coinciden_con_linux_cec_h():
    assert ck.MSG_SIZE == 56
    assert ck.CEC_TRANSMIT == 0xC0386105
    assert ck.CEC_S_MODE == 0x40046109
    assert ck.CEC_ADAP_G_LOG_ADDRS == 0x805C6103
    assert ck.CEC_ADAP_G_PHYS_ADDR == 0x80026101


def test_pide_modo_no_exclusivo_para_convivir_con_kodi():
    adapter = FakeAdapter()
    kernel(adapter).query_power("/dev/cec0")
    assert adapter.mode == ck.CEC_MODE_INITIATOR != 0x02


def test_pregunta_al_televisor_desde_la_direccion_de_kodi():
    adapter = FakeAdapter(log_addr=1)
    kernel(adapter).query_power("/dev/cec0")
    assert adapter.sent == bytes([0x10, ck.OP_GIVE_DEVICE_POWER_STATUS])
    assert adapter.reply_opcode == ck.OP_REPORT_POWER_STATUS


def test_direccion_no_registrada_usa_la_f():
    adapter = FakeAdapter(log_addr=ck.CEC_LOG_ADDR_INVALID)
    kernel(adapter).query_power("/dev/cec0")
    assert adapter.sent[0] == 0xF0


@pytest.mark.parametrize("code, state", [
    (0x00, ck.POWER_ON), (0x01, ck.POWER_STANDBY),
    (0x02, ck.POWER_ON), (0x03, ck.POWER_STANDBY)])
def test_traduce_los_codigos_de_encendido(code, state):
    adapter = FakeAdapter(reply=bytes([0x01, 0x90, code]))
    assert kernel(adapter).query_power("/dev/cec0") == ck.Reading(state, None, "/dev/cec0")


def test_la_respuesta_real_medida_da_standby():
    """019001 es la respuesta capturada de un televisor en standby."""
    adapter = FakeAdapter(reply=bytes.fromhex("019001"))
    assert kernel(adapter).query_power("/dev/cec0").state == ck.POWER_STANDBY


def test_nack_es_desconocido_no_standby():
    """Un televisor desenchufado no contesta: no se puede afirmar que este apagado."""
    adapter = FakeAdapter(tx_status=ck.CEC_TX_STATUS_NACK)
    assert kernel(adapter).query_power("/dev/cec0") == ck.Reading(ck.POWER_UNKNOWN, "nack", "/dev/cec0")


def test_sin_respuesta_es_desconocido():
    adapter = FakeAdapter(rx_status=0x02)
    assert kernel(adapter).query_power("/dev/cec0").error == "no_reply"


@pytest.mark.parametrize("reply, error", [
    (b"\x01\x9e\x04", "unexpected_reply"), (b"\x01\x90", "unexpected_reply"),
    (b"\x01\x90\x07", "bad_power_code")])
def test_respuestas_raras_son_desconocido(reply, error):
    adapter = FakeAdapter(reply=reply)
    assert kernel(adapter).query_power("/dev/cec0") == ck.Reading(ck.POWER_UNKNOWN, error, "/dev/cec0")


def test_adaptador_ocupado_no_revienta_y_cierra():
    adapter = FakeAdapter(busy=True)
    reading = kernel(adapter).query_power("/dev/cec0")
    assert reading == ck.Reading(ck.POWER_UNKNOWN, "EBUSY", "/dev/cec0")
    assert adapter.closed == 1


def test_dispositivo_inexistente():
    adapter = FakeAdapter(missing=True)
    assert kernel(adapter).query_power("/dev/cec9").error == "ENOENT"
    assert adapter.closed == 0


def test_find_adapter_elige_el_que_tiene_algo_conectado():
    adapters = {"/dev/cec0": FakeAdapter(phys=ck.CEC_PHYS_ADDR_INVALID),
                "/dev/cec1": FakeAdapter(phys=0x2000)}
    current = {}

    def open_(path, flags):
        current["a"] = adapters[path]
        return 3

    k = ck.CecKernel(ioctl=lambda fd, req, arg, m=False: current["a"].ioctl(fd, req, arg, m),
                     open_=open_, close=lambda fd: None, exists=lambda p: p in adapters)
    assert k.find_adapter(("/dev/cec0", "/dev/cec1", "/dev/cec2")) == "/dev/cec1"


def test_find_adapter_sin_conexion_devuelve_el_primero_y_sin_dispositivos_none():
    adapter = FakeAdapter(phys=ck.CEC_PHYS_ADDR_INVALID)
    assert kernel(adapter).find_adapter(("/dev/cec0", "/dev/cec1")) == "/dev/cec0"
    assert kernel(adapter, exists=lambda p: False).find_adapter(("/dev/cec0",)) is None
