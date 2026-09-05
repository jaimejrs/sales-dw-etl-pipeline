SELECT nf.id as id_nota_fiscal, 
       inf.id as id_item_nota_fiscal,
       nf.numero_nf, 
       nf.data_venda, 
       inf.id_produto, 
       nf.id_cliente, 
       nf.id_vendedor, 
       nf.id_forma_pagto as id_forma_pagamento,
       inf.quantidade, 
       inf.valor_unitario, 
       inf.valor_venda_real as valor_total_item
FROM vendas.nota_fiscal as nf
LEFT JOIN vendas.item_nota_fiscal inf ON inf.id_nota_fiscal = nf.id;
