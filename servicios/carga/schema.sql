-- Guardián Centinela · esquema de la base (PostgreSQL 16). Idempotente.
CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id            TEXT PRIMARY KEY,
    fecha_registro        DATE,
    pais                  CHAR(2),
    segmento              TEXT CHECK (segmento IN ('persona','comercio_pequeno','comercio_grande')),
    nivel_kyc             SMALLINT CHECK (nivel_kyc BETWEEN 0 AND 3),
    verificado            BOOLEAN,
    edad_cuenta_dias      INTEGER CHECK (edad_cuenta_dias >= 0),
    transacciones_previas INTEGER,
    email_dominio         TEXT,
    email_desechable      BOOLEAN NOT NULL,
    telefono_verificado   BOOLEAN
);

CREATE TABLE IF NOT EXISTS dispositivos (
    dispositivo_id     TEXT PRIMARY KEY,
    tipo               TEXT NOT NULL,
    sistema_operativo  TEXT,
    so_inconsistente   BOOLEAN NOT NULL,
    primera_vez_utc    TIMESTAMPTZ,
    usuarios_distintos INTEGER,
    emulador           BOOLEAN,
    pais_declarado     CHAR(2)
);

CREATE TABLE IF NOT EXISTS lista_negra (
    entrada_id       TEXT PRIMARY KEY,
    tipo             TEXT NOT NULL CHECK (tipo IN ('ip','dispositivo','comercio','tarjeta')),
    valor            TEXT NOT NULL,
    fecha_alta       DATE,
    motivo           TEXT NOT NULL,
    agregado_por     TEXT,
    vigente_inferido BOOLEAN NOT NULL,
    vigente          BOOLEAN NOT NULL,
    UNIQUE (tipo, valor)
);

-- Historial tratado (transacciones evaluadas por el motor actual, con su etiqueta si existe)
CREATE TABLE IF NOT EXISTS transacciones (
    transaccion_id         TEXT PRIMARY KEY,
    usuario_id             TEXT NOT NULL,          -- FK lógica: 598 usuarios no vienen en la muestra
    comercio_id            TEXT,
    dispositivo_id         TEXT REFERENCES dispositivos(dispositivo_id),
    ts_utc                 TIMESTAMPTZ NOT NULL,
    zona_inferida          BOOLEAN NOT NULL,
    monto_original         NUMERIC(14,2) NOT NULL CHECK (monto_original > 0),
    moneda                 CHAR(3) NOT NULL CHECK (moneda IN ('CLP','USD')),
    moneda_inferida        BOOLEAN NOT NULL,
    monto_usd              NUMERIC(14,4) NOT NULL,
    canal                  TEXT NOT NULL,
    mcc                    CHAR(4) NOT NULL,
    pais_transaccion       CHAR(2),
    latitud                DOUBLE PRECISION,
    longitud               DOUBLE PRECISION,
    coordenadas_validas    BOOLEAN NOT NULL,
    ip                     INET,
    ip_valida              BOOLEAN NOT NULL,
    tarjeta_enmascarada    TEXT,                    -- solo últimos 4 dígitos; el PAN nunca llega (RNF5)
    resultado_autorizacion TEXT,
    intentos_previos_1h    INTEGER,
    revisado_por_analista  BOOLEAN NOT NULL,        -- post-decisión: NO se usa para entrenar (fuga R2)
    motivo_bloqueo         TEXT,                    -- post-decisión: NO se usa para entrenar (fuga R2)
    es_fraude              BOOLEAN,                 -- NULL = sin revisar (no es "legítima")
    es_reintento           BOOLEAN NOT NULL,
    usuario_conocido       BOOLEAN NOT NULL,
    en_lista_negra         BOOLEAN NOT NULL,
    tx_usuario_10min       INTEGER NOT NULL,
    tx_usuario_24h         INTEGER NOT NULL,
    tx_dispositivo_1h      INTEGER NOT NULL,
    hora_local             SMALLINT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tx_usuario_ts ON transacciones (usuario_id, ts_utc);
CREATE INDEX IF NOT EXISTS ix_tx_disp_ts    ON transacciones (dispositivo_id, ts_utc);

-- Umbrales versionados: solo INSERT, nunca UPDATE (RF3, RNF10, RO5)
CREATE TABLE IF NOT EXISTS umbrales (
    version          SERIAL PRIMARY KEY,
    umbral_revisar   NUMERIC(4,3) NOT NULL CHECK (umbral_revisar BETWEEN 0 AND 1),
    umbral_bloquear  NUMERIC(4,3) NOT NULL CHECK (umbral_bloquear BETWEEN 0 AND 1),
    politica_reserva TEXT NOT NULL CHECK (politica_reserva IN ('reglas','aprobar','bloquear')),
    modo             TEXT NOT NULL CHECK (modo IN ('sombra','activo')),
    autor            TEXT NOT NULL,
    motivo           TEXT NOT NULL,
    creado_utc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (umbral_revisar < umbral_bloquear)
);

-- Cada decisión del sistema: entrada, resultado, versión del modelo y fecha (RF7, RNF7)
CREATE TABLE IF NOT EXISTS predicciones (
    prediccion_id      BIGSERIAL PRIMARY KEY,
    transaccion_id     TEXT NOT NULL,
    usuario_id         TEXT,
    dispositivo_id     TEXT,
    entrada            JSONB NOT NULL,
    probabilidad       NUMERIC(6,4),
    decision           TEXT NOT NULL CHECK (decision IN ('aprobar','revisar','bloquear')),
    origen             TEXT NOT NULL CHECK (origen IN ('modelo','regla_dura','reserva')),
    razones            JSONB NOT NULL,
    version_modelo     TEXT,
    version_umbrales   INTEGER NOT NULL REFERENCES umbrales(version),
    modo               TEXT NOT NULL,
    replica_ia         TEXT,
    latencia_ms        NUMERIC(10,3),
    creado_utc         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pred_tx      ON predicciones (transaccion_id);
CREATE INDEX IF NOT EXISTS ix_pred_usuario ON predicciones (usuario_id, creado_utc);
CREATE INDEX IF NOT EXISTS ix_pred_fecha   ON predicciones (creado_utc DESC);
