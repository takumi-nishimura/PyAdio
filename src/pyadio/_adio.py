class Adio(object):
    def __init__(self) -> None:
        self.__adc_ch_num: int = 16

    @property
    def ADC_CH_NUM(self):
        return self.__adc_ch_num
