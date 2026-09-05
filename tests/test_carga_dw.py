import unittest

from src.carga_dw import _validar_dataframes_para_carga
from src.transformacao import transformar_dados
from tests.test_transformacao import _dataframes_base


class CargaDWTest(unittest.TestCase):
    def test_validacao_pre_carga_aceita_dataframes_transformados(self):
        dataframes = transformar_dados(_dataframes_base())

        _validar_dataframes_para_carga(dataframes)

    def test_validacao_pre_carga_falha_com_fk_orfa(self):
        dataframes = transformar_dados(_dataframes_base())
        dataframes["fato_vendas"].loc[0, "id_produto"] = 999

        with self.assertRaisesRegex(ValueError, "sem correspondência em dim_produto"):
            _validar_dataframes_para_carga(dataframes)


if __name__ == "__main__":
    unittest.main()
