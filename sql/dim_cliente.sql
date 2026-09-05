WITH CTE_PF AS (
    SELECT p.id as id_cliente, pf.nome AS nome_cliente, 'PF' AS tipo_pessoa, 
           c.descricao as cidade, e.sigla as estado, p.data_cadastro
    FROM geral.pessoa p
    RIGHT JOIN geral.pessoa_fisica pf ON p.id = pf.id
    LEFT JOIN geral.endereco en ON pf.id = en.id_pessoa
    LEFT JOIN geral.bairro b ON b.id = en.id_bairro
    LEFT JOIN geral.cidade c ON c.id = b.id_cidade
    LEFT JOIN geral.estado e ON e.id = c.id_estado
),
CTE_PJ AS (
    SELECT p.id as id_cliente, pj.razao_social AS nome_cliente, 'PJ' AS tipo_pessoa, 
           c.descricao as cidade, e.sigla as estado, p.data_cadastro
    FROM geral.pessoa p
    RIGHT JOIN geral.pessoa_juridica pj ON p.id = pj.id
    LEFT JOIN geral.endereco en ON pj.id = en.id_pessoa
    LEFT JOIN geral.bairro b ON b.id = en.id_bairro
    LEFT JOIN geral.cidade c ON c.id = b.id_cidade
    LEFT JOIN geral.estado e ON e.id = c.id_estado
)
SELECT * FROM CTE_PF
UNION ALL
SELECT * FROM CTE_PJ;