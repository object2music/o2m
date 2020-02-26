from smartcard.scard import *


if __name__ == '__main__':
    hresult, hcontext = SCardEstablishContext(SCARD_SCOPE_USER)

    assert hresult==SCARD_S_SUCCESS

    hresult, readers = SCardListReaders(hcontext, [])

    assert len(readers)>0

    reader = readers[0]

    hresult, hcard, dwActiveProtocol = SCardConnect(
        hcontext,
        reader,
        SCARD_SHARE_SHARED,
        SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1)

    hresult, response = SCardTransmit(hcard,dwActiveProtocol,[0xFF,0xCA,0x00,0x00,0x00])

    print(response)