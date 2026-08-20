// Sample legacy Azure App Service (Linux) app — real source input bundled with the DAF
// deployment so Discovery's Filesystem MCP client has genuine file content to read/parse,
// rather than an empty stub.
const express = require('express')
const sql = require('mssql')
const bodyParser = require('body-parser')

const app = express()
app.use(bodyParser.json())

const port = process.env.PORT || 8080

app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok' })
})

app.get('/invoices', async (req, res) => {
  const pool = await sql.connect(process.env.SQLAZURECONNSTR_InvoiceDb)
  const result = await pool.request().query('SELECT TOP 50 * FROM Invoices ORDER BY CreatedAt DESC')
  res.json(result.recordset)
})

app.listen(port, () => {
  console.log(`legacy-invoice-webapp listening on ${port}`)
})
