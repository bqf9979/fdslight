#!/usr/bin/env python3import pywind.lib.reader as readerimport random, hashlib, base64, osdef gen_handshake_key(key):    """生成websocket握手key    :param key:     :return:     """    sts = "%s258EAFA5-E914-47DA-95CA-C5AB0DC85B11" % key    sha1 = hashlib.sha1(sts.encode("iso-8859-1")).digest()    return base64.b64encode(sha1).decode("iso-8859-1")def bytes2number(byte_data):    v = 0    for n in byte_data: v = (v << 8) | n    return vdef number2bytes(n, fixed_size=0):    seq = []    while n != 0:        t = n & 0xff        seq.insert(0, t)        n = n >> 8    if fixed_size:        size = len(seq)        for i in range(fixed_size - size): seq.insert(0, 0)    return bytes(seq)class DecoderErr(Exception): passclass encoder(object):    slice_size = 4 * 1024    rsv = 0    opcode = 0x2    __server_side = None    def __init__(self, server_side=False):        self.__server_side = server_side    def __codec_data(self, mask_key, byte_data):        seq = []        for ch in byte_data:            n = ch % 4            seq.append(ch ^ mask_key[n])        return seq    def __get_ws_frame(self, fin, opcode, byte_data):        seq = [            ((fin & 0x1) << 7) | ((self.rsv & 0x7) << 4) | (opcode & 0xf),        ]        size = len(byte_data)        mask_key = None        if self.__server_side:            mask = 0        else:            mask = 1            mask_key = os.urandom(4)        if size < 126:            payload = size        elif size < 0x10000:            payload = 126        else:            payload = 127        seq.append(mask | payload)        if mask: seq += list(mask_key)        if mask: seq += self.__codec_data(mask_key, byte_data)        return bytes(seq)    def get_sent_data(self, byte_data):        """获取发送数据"""        seq = []        data_len = len(byte_data)        b, e = (0, self.slice_size,)        while b < data_len:            seq.append(byte_data[b:e])            b, e = (e, e + self.slice_size,)        results = []        bufsize = 0        for data in seq:            wrap_data = self.__get_ws_frame(0, 0, data)            results.append(wrap_data)            bufsize += len(wrap_data)        return (bufsize, b"".join(results),)class decoder(object):    __reader = None    __payload = 0    __read_size = 0    __data_queue = None    __is_start = False    __fin = 0    __rsv = 0    __payload_len = 0    __opcode = 0    __msk_flag = 0    __msk = None    __server_side = False    __parse_step = 1    __data_buff = None    __continue_parse = True    def __init__(self, server_side=False):        self.__reader = reader.reader()        self.__data_queue = []        self.__server_side = server_side        self.__data_buff = []        self.reset()    def __parse_step1(self):        t_a = self.__reader.read(2)        self.__fin = (t_a[0] & 0x80) >> 7        self.__rsv = (t_a[0] & 0x70) >> 4        self.__opcode = t_a[0] & 0xf        self.__msk_flag = (t_a[1] & 0x80) >> 7        self.__payload_len = t_a[1] & 0x7f        self.__parse_step = 2        self.__parse_step2()        if self.__msk_flag == 0 and self.__server_side: raise DecoderErr("client not send mask")    def __parse_step2(self):        min_size = 0        if self.__payload_len < 126:            self.__payload = self.__payload_len            self.__parse_step = 3            self.__parse_step3()            return        if self.__server_side:            min_size = 4        if self.__payload_len == 126:            min_size += 2            psize = 2        else:            min_size += 8            psize = 8        if self.__reader.size() < min_size:            self.__continue_parse = False            return        byte_data = self.__reader.read(psize)        self.__payload = bytes2number(byte_data)        self.__parse_step = 3        self.__parse_step3()        self.__continue_parse = True    def __parse_step3(self):        if not self.__server_side:            self.__parse_step = 4            self.__parse_step4()            return        if self.__server_side and self.__reader.size() < 4:            self.__continue_parse = False            return        self.__msk = self.__reader.read(4)        self.__parse_step = 4        self.__parse_step4()        self.__continue_parse = True    @property    def fin(self):        return self.__fin    @property    def rsv(self):        return self.__rsv    @property    def opcode(self):        return self.__opcode    def __parse_step4(self):        i = self.__read_size        n = self.__payload - self.__read_size        byte_data = self.__reader.read(n)        size = len(byte_data)        self.__read_size += size        if self.__server_side:            tmplist = []            j = 0            while i < self.__read_size:                tmplist.append(byte_data[j] ^ self.__msk[i % 4])                i += 1                j += 1            result = bytes(tmplist)        else:            result = byte_data        self.__data_buff.append(result)    def parse(self):        if not self.__is_start:            min_size = 2            if self.__server_side:                min_size = 6            if self.__reader.size() < min_size:                self.__continue_parse = False                return        if self.__parse_step == 1:            self.__parse_step1()            return        if self.__parse_step == 2:            self.__parse_step2()            return        if self.__parse_step == 3:            self.__parse_step3()            return        if self.__parse_step == 4:            self.__parse_step4()            return        self.__reader.flush()    def input(self, byte_data):        self.__reader._putvalue(byte_data)        self.__continue_parse = True    def reset(self):        self.__parse_step = 1        self.__is_start = False        self.__read_size = 0        self.__payload = 0        self.__continue_parse = True    def frame_ok(self):        """单个帧数据是否解析完        :return:         """        return self.__payload == self.__read_size    def continue_parse(self):        """是否可以继续解析        :return:         """        return self.__continue_parse    def get_data(self):        seq = []        while 1:            try:                seq.append(self.__data_buff.pop(0))            except IndexError:                break        return b"".join(seq)