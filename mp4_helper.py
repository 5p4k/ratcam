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
from picamera.frames import PiVideoFrameType
from io import BytesIO
import struct

UNITY_MATRIX = [0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000]


STATIC_FTYP = Box.build(
    Container(type=b'ftyp')(
        major_brand=b'isom')(
        minor_version=0x200)(
        compatible_brands=[
            b'isom',
            b'iso2',
            b'avc1',
            b'mp41'
        ])
)


STATIC_EMPTY_MDAT = Box.build(Container(type=b'mdat')(data=b''))

NAL_TYPE_SPS = 7
NAL_TYPE_PPS = 8


class MP4Output(object):
    def __init__(self, stream, camera):
        self._stream = stream       # Output stream
        self._camera = camera       # Camera reference
        self._sample_sizes = []     # List of sample sizes, where sps hdr is merged with I-frame
        self._mdat_size = 0         # Total size of the mdat payload
        self._sps_hdr = BytesIO()   # Buffer for processing the sps hdr
        self._seq_parm_sets = []    # All the sequence parm sets found in the stream
        self._pic_parm_sets = []    # All the picture parm sets found in the stream
        self._nal_size_patches = [] # All the points in the stream where we need to patch the NAL size
        # Cached Mp4 attributes
        self._resolution = self._camera.resolution
        self._framerate = self._camera.framerate
        # TODO hardcoded for now
        self._profile = 100
        self._compatibility = 0
        self._level = 40
        self._write_header()

    def _store_size(self, frame_type, frame_size):
        if frame_type == PiVideoFrameType.key_frame:
            assert(len(self._sample_sizes) > 0)
            # Key frames and sps headers are the same sample as far as mp4 is concerned
            self._sample_sizes[-1] += frame_size
        else:
            self._sample_sizes.append(frame_size)
        # At the current _mdat_size offset, we have the beginning of a frame of type
        # frame_type and of size frame_size. That's a NAL unit for which we have to
        # patch the size. The size of the NAL unit is frame size - the actual size field
        self._nal_size_patches.append(self._mdat_size, frame_size - 4)
        self._mdat_size += frame_size

    @staticmethod
    def _get_nal_unit_type(first_nal_byte):
        # The first NAL byte has this structure:
        #   1 forbidden bit (0)
        #   2 bits for nal ref idc
        #   5 bits for nal type
        MASK = (1 << 5) - 1
        return first_nal_byte & MASK

    def _flush_sps_hdr(self, frame_size):
        # The SPS header consists of several NAL units. NAL units are separated by
        # the binary sequence b'\x00\x00\x00\x01'
        self._sps_hdr.seek(0)
        nal_units = self._sps_hdr.read(frame_size).split(b'\x00\x00\x00\x01')
        # We should have only two, SPS and PPS
        assert(len(nal_units) == 3 and len(nal_units[0]) == 0)
        nal_units = nal_units[1:]
        # Scan through all the NALs
        for nal_unit in nal_units:
            nal_unit_type = MP4Output._get_nal_unit_type(nal_unit[0])
            if nal_unit_type == NAL_TYPE_SPS:
                self._seq_parm_sets.append(nal_unit)
            elif nal_unit_type == NAL_TYPE_PPS:
                self._pic_parm_sets.append(nal_unit)
            # Ok now write the size to the stream followed by the NAL
            self._stream.write(struct.pack('>I', len(nal_unit))[-4:])
            self._stream.write(nal_unit)


    def write(self, s):
        # Write the data
        if self._camera.frame.frame_type == PiVideoFrameType.sps_header:
            self._sps_hdr.write(s)
        else:
            # Directly to stream
            self._stream.write(s)

        if self._camera.frame.complete:
            # Store the sizes to assemble the STSZ table afterwards
            self._store_size(self._camera.frame.frame_type, self._camera.frame.frame_size)
            # Patch and flush the SPS header
            if self._camera.frame.frame_type == PiVideoFrameType.sps_header:
                self._flush_sps_hdr(self._camera.frame.frame_size)

    def flush(self):
        # Simplify the sps and pps sections
        self._seq_parm_sets = list(set(self._seq_parm_sets))
        self._pic_parm_sets = list(set(self._pic_parm_sets))
        # Write out the moov section
        self._assemble_moov()
        # And patch the mdat to have the right size
        self._patch_mdat()
        # Patch as well all the frames
        self._patch_nal_unit_sizes()
        # Done.
        self._stream.flush()

    def _write_header(self):
        # Assemble the ftyp header and place an empty mdat block.
        self._stream.write(STATIC_FTYP)
        self._stream.write(STATIC_EMPTY_MDAT)

    def _patch_mdat(self):
        # Move to the position where the mdat size was
        self._stream.seek(len(STATIC_FTYP))
        # Write the actual mdat size as big endian 32 bit integer
        # 8 is the length of the header, <size> + b'mdat'
        self._stream.write(struct.pack('>I', self._mdat_size + 8)[-4:])

    def _patch_nal_unit_sizes(self);
        for offset, size_to_write in self._nal_size_patches:
            self.stream.seek(offset)
            # Write the actual NAL unit size
            self._stream.write(struct.pack('>I', size_to_write)[-4:])

    def _assemble_moov(self):
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

        sample_count = len(self._sample_sizes)
        timescale = self._framerate.numerator
        sample_delta = self._framerate.denominator
        duration = sample_count * sample_delta
        # 8 is the size of <size_block> + b'mdat'
        chunk_offset = len(STATIC_FTYP) + 8
        width = self._resolution[0]
        height = self._resolution[1]
        profile = self._profile
        compatibility = self._compatibility
        level = self._level
        sample_sizes = self._sample_sizes

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
            timescale=timescale)(
            duration=duration)(
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
            entries=[Container(sample_count=sample_count)(sample_delta=sample_delta)])


        AVC1 = Container(format=b'avc1')(
            data_reference_index=1)(
            version=0)(
            revision=0)(
            vendor=b'')(
            temporal_quality=0)(
            spatial_quality=0)(
            width=width)(
            height=height)(
            horizontal_resolution=72)(
            vertical_resolution=72)(
            data_size=0)(
            frame_count=1)(
            compressor_name=b'')(
            depth=24)(
            color_table_id=-1)(
            avc_data=Container(type=b'avcC')(
                version=1)(
                profile=profile)(
                compatibility=compatibility)(
                level=level)(
                nal_unit_length_field=3)(
                sps=self._seq_parm_sets)(
                pps=self._pic_parm_sets))

        STSD = Container(type=b'stsd')(
            version=0)(
            flags=0)(
            entries=[AVC1])

        STSC = Container(type=b'stsc')(
            version=0)(
            flags=0)(
            entries=[
                Container(first_chunk=1)(
                    samples_per_chunk=sample_count)(
                    sample_description_index=1)
            ])

        STCO = Container(type=b'stco')(
            version=0)(
            flags=0)(
            entries=[Container(chunk_offset=chunk_offset)])

        STSZ = Container(type=b'stsz')(
            version=0)(
            flags=0)(
            sample_size=0)(
            sample_count=sample_count)(
            entry_sizes=sample_sizes)

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
            duration=duration)(
            layer=0)(
            alternate_group=0)(
            volume=0)(
            matrix=UNITY_MATRIX)(
            width=width << 16)( # width and height are 16.16 integers
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
            timescale=timescale)(
            duration=duration)(
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

        # Finally write
        self._stream.write(Box.build(MOOV))


