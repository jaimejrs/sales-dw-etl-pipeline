SELECT p.id as id_produto, 
       p.nome as nome_produto, 
       c.descricao as categoria, 
       p.valor_venda, 
       p.valor_custo
FROM vendas.produto as p
LEFT JOIN vendas.categoria as c ON p.id_categoria = c.id;