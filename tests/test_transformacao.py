import unittest

import pandas as pd

from src.transformacao import transformar_dados


def _dataframes_base():
    return {
        "dim_produto": pd.DataFrame(
            [
                {
                    "id_produto": 10,
                    "nome_produto": "Produto A",
                    "categoria": "Categoria A",
                    "valor_venda": 5.0,
                    "valor_custo": 3.0,
                },
                {
                    "id_produto": 10,
                    "nome_produto": "Produto B",
                    "categoria": "Categoria B",
                    "valor_venda": 6.0,
                    "valor_custo": 4.0,
                },
            ]
        ),
        "dim_forma_pagamento": pd.DataFrame(
            [{"id_forma_pagamento": 1, "descricao_forma_pagamento": "Dinheiro"}]
        ),
        "dim_cliente": pd.DataFrame(
            [
                {
                    "id_cliente": 100,
                    "nome_cliente": "Cliente A",
                    "tipo_pessoa": "PF",
                    "cidade": "São Paulo",
                    "estado": "SP",
                    "data_cadastro": "2025-01-01",
                },
                {
                    "id_cliente": 100,
                    "nome_cliente": "Cliente A",
                    "tipo_pessoa": "PF",
                    "cidade": "São Paulo",
                    "estado": "SP",
                    "data_cadastro": "2025-01-01",
                },
            ]
        ),
        "dim_vendedor": pd.DataFrame(
            [{"id_vendedor": 200, "nome_vendedor": "Vendedor A", "data_cadastro": "2024-03-10"}]
        ),
        "fato_vendas": pd.DataFrame(
            [
                {
                    "id_nota_fiscal": 1,
                    "id_item_nota_fiscal": 1000,
                    "numero_nf": "NF-1",
                    "data_venda": "2026-01-15",
                    "id_produto": 10,
                    "id_cliente": 100,
                    "id_vendedor": 200,
                    "id_forma_pagamento": 1,
                    "quantidade": 2,
                    "valor_unitario": 5.0,
                    "valor_total_item": 10.0,
                },
                {
                    "id_nota_fiscal": 1,
                    "id_item_nota_fiscal": 1000,
                    "numero_nf": "NF-1",
                    "data_venda": "2026-01-15",
                    "id_produto": 10,
                    "id_cliente": 100,
                    "id_vendedor": 200,
                    "id_forma_pagamento": 1,
                    "quantidade": 2,
                    "valor_unitario": 5.0,
                    "valor_total_item": 10.0,
                },
                {
                    "id_nota_fiscal": 2,
                    "id_item_nota_fiscal": 2000,
                    "numero_nf": "NF-2",
                    "data_venda": "2026-02-20",
                    "id_produto": None,
                    "id_cliente": 100,
                    "id_vendedor": 200,
                    "id_forma_pagamento": 1,
                    "quantidade": 1,
                    "valor_unitario": 9.0,
                    "valor_total_item": 9.0,
                },
            ]
        ),
    }


class TransformacaoTest(unittest.TestCase):
    def test_transformacao_limpa_fato_dimensoes_e_gera_dim_tempo(self):
        resultado = transformar_dados(_dataframes_base())

        self.assertEqual(len(resultado["fato_vendas"]), 1)
        self.assertEqual(len(resultado["dim_produto"]), 1)
        self.assertEqual(len(resultado["dim_cliente"]), 1)
        self.assertEqual(len(resultado["dim_tempo"]), 1)
        self.assertIn("id_fato_venda", resultado["fato_vendas"].columns)
        self.assertIn("id_tempo", resultado["fato_vendas"].columns)
        self.assertIn("ano_mes", resultado["fato_vendas"].columns)
        self.assertEqual(resultado["dim_tempo"].loc[0, "id_tempo"], 20260115)
        self.assertEqual(resultado["fato_vendas"].loc[0, "ano_mes"], "2026-01")
        self.assertTrue(resultado["fato_vendas"]["id_fato_venda"].is_unique)

    def test_transformacao_nao_muta_dataframes_de_entrada(self):
        entrada = _dataframes_base()

        transformar_dados(entrada)

        self.assertIsInstance(entrada["fato_vendas"].loc[0, "data_venda"], str)
        self.assertNotIn("id_tempo", entrada["fato_vendas"].columns)
        self.assertNotIn("dim_tempo", entrada)

    def test_transformacao_falha_quando_coluna_obrigatoria_nao_existe(self):
        entrada = _dataframes_base()
        entrada["fato_vendas"] = entrada["fato_vendas"].drop(columns=["id_cliente"])

        with self.assertRaisesRegex(ValueError, "Colunas ausentes em fato_vendas"):
            transformar_dados(entrada)

    def test_transformacao_preserva_itens_distintos_da_mesma_nota(self):
        entrada = _dataframes_base()
        entrada["fato_vendas"].loc[1, "id_item_nota_fiscal"] = 1001

        resultado = transformar_dados(entrada)

        self.assertEqual(len(resultado["fato_vendas"]), 2)
        self.assertEqual(set(resultado["fato_vendas"]["id_item_nota_fiscal"]), {1000, 1001})


if __name__ == "__main__":
    unittest.main()
