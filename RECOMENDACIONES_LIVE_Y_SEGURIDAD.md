# 🛡️ Guía de Optimización Cuantitativa, Failsafes y Seguridad para Operatoria en Vivo (Polymarket CLOB)

Este documento detalla la hoja de ruta integral para transformar el motor de **Paper Trading** de **Polymarket 5m BTC Momentum** en un **sistema algorítmico institucional de ejecución en vivo**, priorizando la preservación de capital, la mitigación de latencia y la seguridad criptográfica de claves.

---

## 📐 1. Mejoras Algorítmicas y Cuantitativas

### 1.1. Filtro Dinámico de Spread y Micro-Estructura
* **Problema**: En contratos de 5 minutos, un spread de $0.04 en un token que cotiza a $0.75 representa un costo de fricción inmediato de **5.33%** sobre el capital arriesgado.
* **Optimización**:
  - Implementar un **filtro estricto de spread**:
    ```python
    MAX_SPREAD_ALLOWED = 0.025  # Máximo 2.5 centavos de spread
    if (best_ask - best_bid) > MAX_SPREAD_ALLOWED:
        logging.warning("Spread excesivo ($%.3f) en %s. Entrada omitida.", best_ask - best_bid, slug)
        return
    ```
  - **Filtro de Liquidez Mínima en Top-of-Book**:
    - Verificar que el volumen acumulado en el mejor Ask sea al menos **1.5x a 2x** el tamaño de tu orden antes de disparar.

### 1.2. Feed Cruzado con Spot de Bitcoin (Lead-Lag Arbitrage)
* **Concepto**: El oráculo de liquidación de Polymarket sigue el precio de referencia de fuentes como Binance, Coinbase y Pyth Network.
* **Optimización**:
  - Conectar un WebSocket de baja latencia directo a **Binance Futures / Spot BTCUSDT**.
  - Comparar la distancia entre el precio actual de BTC y el precio strike del intervalo de 5m.
  - **Confirmación cuantitativa**: No entrar únicamente por el precio del token de Polymarket, sino verificar que el *delta* de BTC esté expandiéndose en dirección del trade durante los últimos 15 segundos.

### 1.3. Optimización del Rango de Entrada (Tiering)
Nuestra auditoría de 102 operaciones demostró que:
* **Ask $0.70 – $0.79**: Generó el **70.6% del PnL total** con +$34.17 USD y 74.0% WR (Retorno de +25% a +40% por trade).
* **Ask $0.90 – $0.99**: Aunque tuvo 96.4% de Win Rate, solo generó +$6.09 USD arriesgando $5.00 para ganar entre $0.05 y $0.30.
* **Ajuste sugerido**:
  - Establecer un rango de entrada ideal: **$0.72 <= Ask <= $0.88**.
  - Evitar comprar tokens por encima de **$0.92**, ya que el ratio riesgo/beneficio es altamente desfavorable ante un cisne negro en los últimos segundos.

### 1.4. Salida Inteligente a 20s (Anti-Discount Exit)
* En momentos de volatilidad súbita, a los 20 segundos antes del vencimiento el mejor Bid puede caer transitoriamente a $0.85 aunque la posición esté ganando.
* **Regla de Ejecución**:
  ```python
  # Si faltan 20s y el Bid es >= 0.95, salir y embolsar.
  # Si el Bid está entre 0.85 y 0.94 pero la distancia de BTC al strike es amplia (> $30), 
  # esperar 10s adicionales antes de forzar la salida a mercado.
  ```

---

## 🔒 2. Seguridad Operativa y Gestión de Claves (OpSec)

### 2.1. Arquitectura de Hot Wallet Aislada (Zero-Contagion)
* ⚠️ **REGLA DE ORO**: **JAMÁS** uses la clave privada de tu wallet personal, Ledger, o cuenta con ahorros principales.
* **Configuración de Producción**:
  1. Generar una **cuenta de Ethereum/Polygon completamente nueva** dedicada exclusivamente a este bot.
  2. Fondearla únicamente con el capital asignado a la estrategia (ej. $100 a $300 USDC.e en Polygon PoS).
  3. Si la clave privada de la hot wallet se viese comprometida por cualquier motivo, el daño máximo está estrictamente acotado al saldo operativo.

### 2.2. Gestión Segura de Credenciales con py-clob-client
Polymarket utiliza una arquitectura híbrida:
1. **Firma L1 (Clave Privada)**: Se usa una sola vez para derivar las credenciales API.
2. **Credenciales L2 (API Key, Secret, Passphrase)**: Se usan para autenticar las llamadas REST/WebSocket al motor de calce.

#### Estructura Segura recomendada:
```bash
# Archivo .env (fuera de control de versiones .gitignore)
POLYMARKET_PK=0x...          # Clave privada de la hot wallet
POLYMARKET_API_KEY=...       # API Key L2
POLYMARKET_API_SECRET=...    # Secret L2
POLYMARKET_PASSPHRASE=...    # Passphrase L2
```

---

## 🛡️ 3. Failsafes, Circuit Breakers y Kill-Switches

Para operar desatendido toda la semana, el sistema debe ser capaz de autoprotegerse sin intervención humana ante escenarios adversos:

### 3.1. Max Daily Drawdown Stop (Kill-Switch Diario)
Si la cuenta experimenta una caída mayor al **10% del balance inicial del día**, el bot cancela todas las órdenes activas, liquida posiciones abiertas y se apaga hasta la medianoche:
```python
if (starting_day_equity - current_equity) >= (starting_day_equity * 0.10):
    send_ntfy("EMERGENCIA: Circuit Breaker activado por pérdida del 10%. Apagando bot.", title="KILL SWITCH")
    sys.exit(1)
```

### 3.2. Consecutivos Loser Cooldown
* Si se acumulan **3 operaciones perdedoras seguidas**, indica que el mercado está en un régimen de alta turbulencia o desfasaje con el oráculo.
* El bot debe entrar en un **enfriamiento de 30 minutos** (saltándose las siguientes 6 ventanas de 5m) para permitir que la microestructura se estabilice.

### 3.3. Heartbeat & Watchdog (Supervisor de Vida)
* El bot debe registrar un timestamp (heartbeat) en memoria o archivo cada 10 segundos.
* Si el bucle principal no registra actividad durante más de 45 segundos (congelamiento de sockets o timeout de API), el supervisor reinicia el servicio y envía un push de alerta a tu iPhone.

---

## 🖥️ 4. Configuración del Host para Operatoria 24/7 toda la Semana

Si dejás la máquina corriendo toda la semana desde tu casa, Windows tiene mecanismos de ahorro de energía que debés desactivar para evitar que la red o el CPU se suspendan:

### 4.1. Desactivar Suspensión en Windows (PowerShell Administrador)
```powershell
# Desactivar suspensión automática con corriente alterna
powercfg -change -standby-timeout-ac 0
# Desactivar hibernación
powercfg -change -hibernate-timeout-ac 0
```

### 4.2. Pausar Actualizaciones Automáticas de Windows Update
* Windows Update puede reiniciar la PC durante la noche.
* En **Configuración** -> **Windows Update** -> Seleccioná **Pausar actualizaciones durante 1 semana**.

---

## 🚀 5. Checklist Pre-Vuelo para Operatoria en Real

- [ ] **Hot Wallet dedicada** creada con clave privada exclusiva.
- [ ] Fondeo acotado (máximo $50 - $100 USDC iniciales para fase piloto).
- [ ] Gas en Polygon (mínimo 2 a 5 POL para comisiones si fuesen necesarias).
- [ ] Archivo `.gitignore` verificado (confirmar que `.env` y claves no estén en git).
- [ ] Filtro de spread estricto (máximo $0.025).
- [ ] Filtro de rango de entrada ($0.72 a $0.88).
- [ ] Circuit Breaker del 10% diario y Cooldown de 3 rachas negativas configurados.
- [ ] Notificaciones push de **ntfy** probadas en tu iPhone.
- [ ] Windows configurado para no suspenderse (pantalla puede apagarse, CPU debe seguir activo).
