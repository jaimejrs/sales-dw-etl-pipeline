SELECT DISTINCT nf.id_vendedor AS id_vendedor,
       pf.nome AS nome_vendedor,
       p.data_cadastro
FROM vendas.nota_fiscal nf
LEFT JOIN geral.pessoa p ON p.id = nf.id_vendedor
LEFT JOIN geral.pessoa_fisica pf ON pf.id = p.id
WHERE nf.id_vendedor IS NOT NULL;
