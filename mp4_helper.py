#
# Copyright (C) 2017  Pietro Saccardi

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from pymp4.parser import Box
from construct import Container

UNITY_MATRIX = [0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000]


def build_mp4_header_and_footer(duration_in_units, units_per_sec, width, height):
    # The mandatory hierarchy for a minimal MP4 file

    #   ftyp
    #   mdat
    #   moov
    #    +- mvhd
    #    +- trak
    #        +- tkhd
    #        +- mdia
    #            +- mdhd
    #            +- hdlr

    FTYP = Container(type=b'ftyp')(
        major_brand=b'isom')(
        minor_version=0x200)(
        compatible_brands=[
            b'isom',
            b'iso2',
            b'avc1',
            b'mp41'
        ])

    HDLR = Container(type=b'hdlr')(
        version=0)(
        flags=0)(
        handler_type=b'vide')(
        name='Raspicam Video')

    MDHD = Container(type=b'mdhd')(
        version=0)(
        flags=0)(
        creation_time=0)(
        modification_time=0)(
        timescale=units_per_sec)(
        duration=duration_in_units)(
        language='und')

    MDIA = Container(type=b'mdia')(
        children=[
            MDHD,
            HDLR
        ])

    TKHD = Container(type=b'tkhd')(
        version=0)(
        flags=3)(
        creation_time=0)(
        modification_time=0)(
        track_ID=1)(
        duration=duration_in_units)(
        layer=0)(
        alternate_group=0)(
        volume=0)(
        matrix=UNITY_MATRIX)(
        width=width << 16)(
        height=height << 16)

    TRAK = Container(type=b'trak')(
        children=[
            TKHD,
            MDIA
        ])


    MVHD = Container(type=b'mvhd')(
        version=0)(
        flags=0)(
        creation_time=0)(
        modification_time=0)(
        timescale=units_per_sec)(
        duration=duration_in_units)(
        rate=0x10000)(
        volume=0x100)(
        matrix=UNITY_MATRIX)(
        pre_defined=[0, 0, 0, 0, 0, 0])(
        next_track_ID=2)

    MOOV = Container(type=b'moov')(
        children=[
            MVHD,
            TRAK
        ])

    return (Box.build(FTYP), Box.build(MOOV))