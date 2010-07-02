#!/usr/bin/python
#
# Copyright 2010 Dan Smith <dsmith@danplanet.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import threading

from chirp import chirp_common, errors

DEBUG = True

DUPLEX = { 0 : "", 1 : "+", 2 : "-" }
MODES = { 0 : "FM", 1 : "AM" }
STEPS = list(chirp_common.TUNING_STEPS)
STEPS.append(100.0)

def rev(hash, value):
    reverse = {}
    for k, v in hash.items():
        reverse[v] = k

    return reverse[value]

LOCK = threading.Lock()

def command(s, command, *args):
    global LOCK

    LOCK.acquire()
    cmd = command
    if args:
        cmd += " " + " ".join(args)
    if DEBUG:
        print "PC->D7: %s" % cmd
    s.write(cmd + "\r")

    result = ""
    while not result.endswith("\r"):
        result += s.read(8)

    if DEBUG:
        print "D7->PC: %s" % result.strip()

    LOCK.release()

    return result.strip()

def get_id(s):
    r = command(s, "ID")
    if " " in r:
        return r.split(" ")[1]
    else:
        raise errors.RadioError("No response from radio")

def get_tmode(tone, ctcss, dcs):
    if dcs and int(dcs) == 1:
        return "DTCS"
    elif int(ctcss):
        return "TSQL"
    elif int(tone):
        return "Tone"
    else:
        return ""

def iserr(result):
    return result in ["N", "?"]

class KenwoodLiveRadio(chirp_common.LiveRadio):
    BAUD_RATE = 9600
    VENDOR = "Kenwood"
    MODEL = ""

    _vfo = 0
    mem_upper_limit = 200

    def __init__(self, *args, **kwargs):
        chirp_common.LiveRadio.__init__(self, *args, **kwargs)

        self.pipe.setTimeout(0.1)

        self.__memcache = {}

        self.__id = get_id(self.pipe)
        print "Talking to a %s" % self.__id

        command(self.pipe, "AI", "0")

    def get_memory(self, number):
        if number < 0 or number >= self.mem_upper_limit:
            raise errors.InvalidMemoryLocation("Number must be between 0 and 200")
        if self.__memcache.has_key(number):
            return self.__memcache[number]

        result = command(self.pipe, "MR", "%i,0,%03i" % (self._vfo, number + 1))
        if result == "N":
            mem = chirp_common.Memory()
            mem.number = number
            mem.empty = True
            return mem
        elif " " not in result:
            print "Not sure what to do with this: `%s'" % result
            raise errors.RadioError("Unexpected result returned from radio")

        value = result.split(" ")[1]
        spec = value.split(",")

        mem = self._parse_mem_spec(spec)
        self.__memcache[mem.number] = mem

        result = command(self.pipe, "MNA", "%i,%03i" % (self._vfo, number + 1))
        if " " in result:
            value = result.split(" ")[1]
            zero, loc, mem.name = value.split(",")
 
        return mem

    def _make_mem_spec(self, mem):
        pass

    def _parse_mem_spec(self, spec):
        pass

    def set_memory(self, memory):
        if memory.number < 0 or memory.number >= self.mem_upper_limit:
            raise errors.InvalidMemoryLocation("Number must be between 0 and 200")

        spec = self._make_mem_spec(memory)
        r1 = command(self.pipe, "MW", ",".join(spec))
        if not iserr(r1):
            r2 = command(self.pipe, "MNA", "%i,%03i,%s" % (self._vfo,
                                                           memory.number + 1,
                                                           memory.name))
            if not iserr(r2):
                self.__memcache[memory.number] = memory

    def get_memory_upper(self):
        return self.mem_upper_limit - 1

    def filter_name(self, name):
        return chirp_common.name8(name)

    def erase_memory(self, number):
        r = command(self.pipe, "MW", "%i,0,%03i" % (self._vfo, number+1))
        if iserr(r):
            raise errors.RadioError("Radio refused delete of %i" % number)

class THD7Radio(KenwoodLiveRadio):
    MODEL = "TH-D7(a)(g)"

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_dtcs = False
        rf.has_dtcs_polarity = False
        rf.has_bank = False
        rf.has_mode = False
        rf.has_tuning_step = False
        rf.valid_modes = MODES.values()
        return rf

    def _make_mem_spec(self, mem):
        spec = ( \
            "0",
            "0",
            "%03i" % (mem.number + 1),
            "%011i" % (mem.freq * 1000000),
            "%i" % STEPS.index(mem.tuning_step),
            "%i" % rev(DUPLEX, mem.duplex),
            "0",
            "%i" % (mem.tmode == "Tone"),
            "%i" % (mem.tmode == "TSQL"),
            "", # DCS Flag
            "%02i" % (chirp_common.TONES.index(mem.rtone) + 1),
            "", # DCS Code
            "%02i" % (chirp_common.TONES.index(mem.ctone) + 1),
            "%09i" % (mem.offset * 1000000),
            "%i" % rev(MODES, mem.mode),
            "0")

        return spec

    def _parse_mem_spec(self, spec):
        mem = chirp_common.Memory()

        mem.number = int(spec[2]) - 1
        mem.freq = int(spec[3]) / 1000000.0
        mem.tuning_step = STEPS[int(spec[4])]
        mem.duplex = DUPLEX[int(spec[5])]
        mem.tmode = get_tmode(spec[7], spec[8], spec[9])
        mem.rtone = chirp_common.TONES[int(spec[10]) - 1]
        mem.ctone = chirp_common.TONES[int(spec[12]) - 1]
        if spec[11] and spec[11].isdigit():
            mem.dtcs = chirp_common.DTCS_CODES[int(spec[11][:-1]) - 1]
        else:
            print "Unknown or invalid DCS: %s" % spec[11]
        if spec[13]:
            mem.offset = int(spec[13]) / 1000000.0
        else:
            mem.offset = 0.0
        mem.mode = MODES[int(spec[14])]

        return mem

class TMD700Radio(KenwoodLiveRadio):
    MODEL = "TH-D700"

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_dtcs = False
        rf.has_dtcs_polarity = False
        rf.has_bank = False
        rf.has_mode = False
        rf.has_tuning_step = False
        rf.valid_modes = MODES.values()
        return rf

    def _make_mem_spec(self, mem):
        spec = ( \
            "0",
            "0",
            "%03i" % (mem.number + 1),
            "%011i" % (mem.freq * 1000000),
            "%i" % STEPS.index(mem.tuning_step),
            "%i" % rev(DUPLEX, mem.duplex),
            "0",
            "%i" % (mem.tmode == "Tone"),
            "%i" % (mem.tmode == "TSQL"),
            "%i" % (mem.tmode == "DTCS"),
            "%02i" % (chirp_common.TONES.index(mem.rtone) + 1),
            "%03i0" % (chirp_common.DTCS_CODES.index(mem.dtcs) + 1),
            "%02i" % (chirp_common.TONES.index(mem.ctone) + 1),
            "%09i" % (mem.offset * 1000000),
            "%i" % rev(MODES, mem.mode),
            "0")

        return spec

    def _parse_mem_spec(self, spec):
        mem = chirp_common.Memory()

        mem.number = int(spec[2]) - 1
        mem.freq = int(spec[3]) / 1000000.0
        mem.tuning_step = STEPS[int(spec[4])]
        mem.duplex = DUPLEX[int(spec[5])]
        mem.tmode = get_tmode(spec[7], spec[8], spec[9])
        mem.rtone = chirp_common.TONES[int(spec[10]) - 1]
        mem.ctone = chirp_common.TONES[int(spec[12]) - 1]
        if spec[11] and spec[11].isdigit():
            mem.dtcs = chirp_common.DTCS_CODES[int(spec[11][:-1]) - 1]
        else:
            print "Unknown or invalid DCS: %s" % spec[11]
        if spec[13]:
            mem.offset = int(spec[13]) / 1000000.0
        else:
            mem.offset = 0.0
        mem.mode = MODES[int(spec[14])]

        return mem

class TMV7Radio(KenwoodLiveRadio):
    MODEL = "TM-V7"

    mem_upper_limit = 90

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_dtcs = False
        rf.has_dtcs_polarity = False
        rf.has_bank = False
        rf.has_mode = False
        rf.has_tuning_step = False
        rf.valid_modes = ["FM"]
        rf.has_sub_devices = True
        return rf

    def _make_mem_spec(self, mem):
        spec = ( \
            "%i" % self._vfo,
            "0",
            "%03i" % (mem.number + 1),
            "%011i" % (mem.freq * 1000000),
            "%i" % STEPS.index(mem.tuning_step),
            "%i" % rev(DUPLEX, mem.duplex),
            "0",
            "%i" % (mem.tmode == "Tone"),
            "%i" % (mem.tmode == "TSQL"),
            "0",
            "%02i" % (chirp_common.TONES.index(mem.rtone) + 1),
            "000",
            "%02i" % (chirp_common.TONES.index(mem.ctone) + 1),
            "",
            "0")

        return spec

    def _parse_mem_spec(self, spec):
        mem = chirp_common.Memory()
        mem.number = int(spec[2]) - 1
        mem.freq = int(spec[3]) / 1000000.0
        mem.tuning_step = STEPS[int(spec[4])]
        mem.duplex = DUPLEX[int(spec[5])]
        if int(spec[7]):
            mem.tmode = "Tone"
        elif int(spec[8]):
            mem.tmode = "TSQL"
        mem.rtone = chirp_common.TONES[int(spec[10]) - 1]
        mem.ctone = chirp_common.TONES[int(spec[12]) - 1]

        return mem

    def filter_name(self, name):
        return name[:7]

    def get_sub_devices(self):
        return [TMV7RadioVHF(self.pipe), TMV7RadioUHF(self.pipe)]

class TMV7RadioVHF(TMV7Radio):
    VARIANT = "VHF"
    _vfo = 0

class TMV7RadioUHF(TMV7Radio):
    VARIANT = "UHF"
    _vfo = 1

if __name__ == "__main__":
    import serial
    import sys

    s = serial.Serial(port=sys.argv[1], baudrate=9600, xonxoff=True, timeout=1)

    print get_id(s)
    print get_memory(s, int(sys.argv[2]))
