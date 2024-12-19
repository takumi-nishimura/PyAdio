from unittest.mock import MagicMock, patch

from pyadio.pyadio import PyAdio


def test_close():
    with patch("pyadio.pyadio.Serial") as mock_serial:
        mock_instance = mock_serial.return_value
        pyadio_instance = PyAdio(port="COM3")
        pyadio_instance.close()
        mock_instance.close.assert_called_once()
