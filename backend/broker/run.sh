#!/bin/bash
echo "═══════════════════════════════════"
echo " KAT IBKR Bridge"
echo " Paper: TWS port 7497"
echo "═══════════════════════════════════"
echo ""

# Check TWS is running
if ! nc -z 127.0.0.1 7497 2>/dev/null; then
    echo "⚠️  TWS not detected on port 7497"
    echo "   Open TWS → File → Global Configuration → API → Settings"
    echo "   Enable 'ActiveX and Socket Clients', port 7497"
    echo ""
    read -p "Press Enter when TWS is ready..."
fi

python3 ibkr_bridge.py
