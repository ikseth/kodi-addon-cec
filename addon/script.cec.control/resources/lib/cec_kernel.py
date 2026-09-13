"""Lectura del estado de encendido del televisor por el API CEC del kernel.

No importa nada de Kodi, para poder testearlo. Ver docs/DESIGN.md: el adaptador
se abre en modo iniciador NO exclusivo, que el kernel concede en paralelo al modo
exclusivo con el que libCEC (dentro de Kodi) lo mantiene abierto. Asi se puede
preguntar al televisor sin desalojar a Kodi.

Las llamadas al sistema (open, close, ioctl, exists) se inyectan en CecKernel
para que los tests puedan simular un adaptador.
"""
import array
import errno
import fcntl
import os
import struct

_IOC_WRITE = 1
_IOC_READ = 2
_CEC_IOC_TYPE = ord("a")


def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (_CEC_IOC_TYPE << 8) | nr


# struct cec_msg (linux/cec.h): 56 bytes.
MSG_FORMAT = "QQIIII16sBBBBBBBx"
MSG_SIZE = struct.calcsize(MSG_FORMAT)
_OFFSET_LEN = 16
_OFFSET_MSG = 32
_OFFSET_REPLY = 48
_OFFSET_RX_STATUS = 49
_OFFSET_TX_STATUS = 50

LOG_ADDRS_SIZE = 92  # struct cec_log_addrs

CEC_ADAP_G_PHYS_ADDR = _ioc(_IOC_READ, 1, 2)
CEC_ADAP_G_LOG_ADDRS = _ioc(_IOC_READ, 3, LOG_ADDRS_SIZE)
CEC_TRANSMIT = _ioc(_IOC_READ | _IOC_WRITE, 5, MSG_SIZE)
CEC_S_MODE = _ioc(_IOC_WRITE, 9, 4)

CEC_MODE_INITIATOR = 0x01          # NO exclusivo: el exclusivo (0x02) lo tiene Kodi
CEC_PHYS_ADDR_INVALID = 0xFFFF     # adaptador sin nada conectado
CEC_LOG_ADDR_TV = 0x0
CEC_LOG_ADDR_UNREGISTERED = 0xF
CEC_LOG_ADDR_INVALID = 0xFF

CEC_TX_STATUS_OK = 0x01
CEC_TX_STATUS_NACK = 0x04
CEC_RX_STATUS_OK = 0x01

OP_GIVE_DEVICE_POWER_STATUS = 0x8F
OP_REPORT_POWER_STATUS = 0x90

POWER_ON = "on"
POWER_STANDBY = "standby"
POWER_UNKNOWN = "unknown"

# Codigos de REPORT_POWER_STATUS. Las transiciones se reportan con su destino.
_POWER_CODES = {
    0x00: POWER_ON,
    0x01: POWER_STANDBY,
    0x02: POWER_ON,        # pasando de standby a encendido
    0x03: POWER_STANDBY,   # pasando de encendido a standby
}


class Reading(object):
    """Resultado de una consulta. `error` es None si se obtuvo un estado."""

    __slots__ = ("state", "error", "device")

    def __init__(self, state, error, device):
        self.state = state
        self.error = error
        self.device = device

    def __eq__(self, other):
        return isinstance(other, Reading) and (
            (self.state, self.error, self.device)
            == (other.state, other.error, other.device))

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "Reading(state=%r, error=%r, device=%r)" % (
            self.state, self.error, self.device)


def build_message(origin, destination, opcode):
    return bytes([((origin & 0x0F) << 4) | (destination & 0x0F), opcode])


def pack_transmit(message, reply_opcode, timeout_ms):
    return struct.pack(MSG_FORMAT, 0, 0, len(message), timeout_ms, 0, 0,
                       message.ljust(16, b"\0"), reply_opcode, 0, 0, 0, 0, 0, 0)


def parse_transmit(raw):
    """Devuelve (tx_status, rx_status, cuerpo_de_la_respuesta)."""
    length = struct.unpack_from("I", raw, _OFFSET_LEN)[0]
    body = bytes(raw[_OFFSET_MSG:_OFFSET_MSG + min(length, 16)])
    return raw[_OFFSET_TX_STATUS], raw[_OFFSET_RX_STATUS], body


def interpret(tx_status, rx_status, body):
    """Traduce el resultado de CEC_TRANSMIT a (estado, error)."""
    if not tx_status & CEC_TX_STATUS_OK:
        # NACK: nadie contesta en la direccion del televisor (apagado de la
        # corriente o sin CEC). No es lo mismo que "standby".
        return POWER_UNKNOWN, "nack" if tx_status & CEC_TX_STATUS_NACK else "tx_error"
    if not rx_status & CEC_RX_STATUS_OK:
        return POWER_UNKNOWN, "no_reply"
    if len(body) < 3 or body[1] != OP_REPORT_POWER_STATUS:
        return POWER_UNKNOWN, "unexpected_reply"
    state = _POWER_CODES.get(body[2])
    if state is None:
        return POWER_UNKNOWN, "bad_power_code"
    return state, None


def _error_name(exc):
    return errno.errorcode.get(getattr(exc, "errno", None), "oserror")


class CecKernel(object):

    def __init__(self, ioctl=fcntl.ioctl, open_=os.open, close=os.close,
                 exists=os.path.exists):
        self._ioctl = ioctl
        self._open = open_
        self._close = close
        self._exists = exists

    def physical_address(self, fd):
        buf = array.array("H", [0])
        self._ioctl(fd, CEC_ADAP_G_PHYS_ADDR, buf, True)
        return buf[0]

    def logical_address(self, fd):
        buf = array.array("B", bytes(LOG_ADDRS_SIZE))
        self._ioctl(fd, CEC_ADAP_G_LOG_ADDRS, buf, True)
        address = buf[0]
        if address == CEC_LOG_ADDR_INVALID:
            return CEC_LOG_ADDR_UNREGISTERED
        return address & 0x0F

    def find_adapter(self, candidates):
        """Primer adaptador con algo conectado (direccion fisica valida).

        Si ninguno la tiene, el primero que exista; si no existe ninguno, None.
        """
        existing = [path for path in candidates if self._exists(path)]
        for path in existing:
            try:
                fd = self._open(path, os.O_RDWR)
            except OSError:
                continue
            try:
                if self.physical_address(fd) != CEC_PHYS_ADDR_INVALID:
                    return path
            except OSError:
                pass
            finally:
                self._close(fd)
        return existing[0] if existing else None

    def query_power(self, device, timeout_ms=1000):
        try:
            fd = self._open(device, os.O_RDWR)
        except OSError as exc:
            return Reading(POWER_UNKNOWN, _error_name(exc), device)
        try:
            self._ioctl(fd, CEC_S_MODE, struct.pack("I", CEC_MODE_INITIATOR))
            origin = self.logical_address(fd)
            message = build_message(origin, CEC_LOG_ADDR_TV, OP_GIVE_DEVICE_POWER_STATUS)
            buf = array.array("B", pack_transmit(message, OP_REPORT_POWER_STATUS, timeout_ms))
            self._ioctl(fd, CEC_TRANSMIT, buf, True)
            state, error = interpret(*parse_transmit(bytes(buf)))
            return Reading(state, error, device)
        except OSError as exc:
            return Reading(POWER_UNKNOWN, _error_name(exc), device)
        finally:
            self._close(fd)
