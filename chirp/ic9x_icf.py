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

from chirp import chirp_common, icf, ic9x_icf_ll

class IC9xICFRadio(chirp_common.CloneModeRadio):
    VENDOR = "Icom"
    MODEL = "IC-9x"
    VARIANT = "ICF File"

    _upper = 1200

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_bank_index = True
        rf.memory_bounds = (0, self._upper)
        rf.has_sub_devices = True
        return rf

    def get_memory(self, number):
        return ic9x_icf_ll.get_memory(self._mmap, number)

    def load_mmap(self, filename):
        mdata, self._mmap = icf.read_file(filename)

    def get_sub_devices(self):
        return [IC9xICFRadioA(self._mmap),
                IC9xICFRadioB(self._mmap)]

class IC9xICFRadioA(IC9xICFRadio):
    VARIANT = "ICF File Band A"

    _upper = 800

    def get_memory(self, number):
        if number > self._upper:
            raise errors.InvalidMemoryLocation("Number must be <800")

        return ic9x_icf_ll.get_memory(self._mmap, number)

class IC9xICFRadioB(IC9xICFRadio):
    VARIANT = "ICF File Band B"

    _upper = 400

    def get_memory(self, number):
        if number > self._upper:
            raise errors.InvalidMemoryLocation("Number must be <400")

        mem = ic9x_icf_ll.get_memory(self._mmap, 850 + number)
        mem.number = number
        return mem