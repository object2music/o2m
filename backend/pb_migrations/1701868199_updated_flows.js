migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "s0liarni",
    "name": "max_results",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // remove
  collection.schema.removeField("s0liarni")

  return dao.saveCollection(collection)
})
