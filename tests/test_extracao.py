import unittest

from src.extracao import _aplicar_filtro_incremental_fato


class ExtracaoTest(unittest.TestCase):
    def test_filtro_incremental_remove_ponto_virgula_e_filtra_data_venda(self):
        query = "SELECT * FROM vendas.nota_fiscal nf;"

        query_incremental = _aplicar_filtro_incremental_fato(query)

        self.assertNotIn(";", query_incremental)
        self.assertIn("WHERE nf.data_venda >= :data_inicio_incremental", query_incremental)


if __name__ == "__main__":
    unittest.main()
