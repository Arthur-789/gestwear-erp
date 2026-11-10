-- =====================================================================
-- Adiciona o código curto de categorias e cores (usado na composição do SKU)
-- em bancos criados antes desta coluna existir.
-- =====================================================================
BEGIN;

ALTER TABLE categorias ADD COLUMN codigo VARCHAR(5);
ALTER TABLE cores ADD COLUMN codigo VARCHAR(4);

UPDATE categorias SET codigo = CASE nome
    WHEN 'Camisetas' THEN 'CAM'
    WHEN 'Camisas' THEN 'CMS'
    WHEN 'Calças' THEN 'CAL'
    WHEN 'Bermudas e Shorts' THEN 'BER'
    WHEN 'Vestidos e Saias' THEN 'VES'
    WHEN 'Agasalhos' THEN 'AGA'
    WHEN 'Íntimas e Meias' THEN 'INT'
    WHEN 'Acessórios' THEN 'ACE'
END;

UPDATE cores SET codigo = CASE nome
    WHEN 'Branco' THEN 'BR'
    WHEN 'Preto' THEN 'PT'
    WHEN 'Cinza' THEN 'CZ'
    WHEN 'Azul' THEN 'AZ'
    WHEN 'Azul Marinho' THEN 'MR'
    WHEN 'Vermelho' THEN 'VM'
    WHEN 'Verde' THEN 'VD'
    WHEN 'Bege' THEN 'BG'
    WHEN 'Rosa' THEN 'RS'
    WHEN 'Amarelo' THEN 'AM'
    WHEN 'Marrom' THEN 'MA'
    WHEN 'Jeans Claro' THEN 'JC'
    WHEN 'Jeans Escuro' THEN 'JE'
END;

-- Registros adicionais, se existirem, recebem um código provisório
UPDATE categorias SET codigo = 'C' || id WHERE codigo IS NULL;
UPDATE cores SET codigo = 'K' || id WHERE codigo IS NULL;

ALTER TABLE categorias ALTER COLUMN codigo SET NOT NULL;
ALTER TABLE categorias ADD CONSTRAINT categorias_codigo_key UNIQUE (codigo);
ALTER TABLE categorias ADD CONSTRAINT categorias_codigo_check CHECK (codigo ~ '^[A-Z0-9]{2,5}$');

ALTER TABLE cores ALTER COLUMN codigo SET NOT NULL;
ALTER TABLE cores ADD CONSTRAINT cores_codigo_key UNIQUE (codigo);
ALTER TABLE cores ADD CONSTRAINT cores_codigo_check CHECK (codigo ~ '^[A-Z0-9]{1,4}$');

COMMIT;
