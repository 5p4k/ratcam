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


def build_mp4_header_and_footer(units_per_sec, frame_rate_per_sec,
    width, height, profile, compatibility, level, frame_sizes):
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
    #            +- minf
    #                +- dinf
    #                    +- dref
    #                +- stbl
    #                    +- stsd
    #                    +- stts
    #                    +- stsc
    #                    +- stco
    #                    +- stsz

    num_frames = len(frame_sizes)
    duration_in_units = num_frames * units_per_sec // frame_rate_per_sec

    FTYP = Container(type=b'ftyp')(
        major_brand=b'isom')(
        minor_version=0x200)(
        compatible_brands=[
            b'isom',
            b'iso2',
            b'avc1',
            b'mp41'
        ])

    built_ftyp = Box.build(FTYP)

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

    DREF = Container(type=b'dref')(
        version=0)(
        flags=0)(
        data_entries=[
            Container(type=b'url ')(
                version=0)(
                flags=Container(self_contained=True))(
                location=None)
        ])

    DINF = Container(type=b'dinf')(children=[DREF])

    STTS = Container(type=b'stts')(
        version=0)(
        flags=0)(
        entries=[Container(sample_count=num_frames)(sample_delta=frame_rate_per_sec)])


    AVC1 = Container(format=b'avc1')(
        data_reference_index=1)(
        version=0)(
        revision=0)(
        # vendor=b'\x00\x00\x00\x00')(
        vendor=b'')(
        temporal_quality=0)(
        spatial_quality=0)(
        width=640)(
        height=480)(
        horizontal_resolution=72)(
        vertical_resolution=72)(
        data_size=0)(
        frame_count=1)(
        # compressor_name=b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')(
        compressor_name=b'')(
        depth=24)(
        color_table_id=-1)(
        avc_data=Container(type=b'avcC')(
            version=1)(
            profile=profile)(
            compatibility=compatibility)(
            level=level)(
            nal_unit_length_field=3)(
            sps=[b"'d\x00(\xac+@P\x1e\xd0\x0f\x12&\xa0"])(
            # sps=[])(
            pps=[b'(\xee\x01\x0f,']))
            # pps=[]))

    STSD = Container(type=b'stsd')(
        version=0)(
        flags=0)(
        entries=[AVC1])

    STSC = Container(type=b'stsc')(
        version=0)(
        flags=0)(
        entries=[
            Container(first_chunk=1)(
                samples_per_chunk=num_frames)(
                sample_description_index=1)
        ])

    STCO = Container(type=b'stco')(
        version=0)(
        flags=0)(
        entries=[Container(
            chunk_offset=len(built_ftyp)
        )])

    STSZ = Container(type=b'stsz')(
        version=0)(
        flags=0)(
        sample_size=0)(
        sample_count=num_frames)(
        entry_sizes=frame_sizes)

    STBL = Container(type=b'stbl')(
        children=[
            STSD,
            STTS,
            STSC,
            STSZ,
            STCO
        ])

    VMHD = Container(type=b'vmhd')(
        version=0)(
        flags=1)(
        graphics_mode=0)(
        opcolor=Container(red=0)(green=0)(blue=0))

    MINF = Container(type=b'minf')(
        children=[
            VMHD,
            DINF,
            STBL
        ])

    MDIA = Container(type=b'mdia')(
        children=[
            MDHD,
            HDLR,
            MINF
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

    return (built_ftyp, Box.build(MOOV))
