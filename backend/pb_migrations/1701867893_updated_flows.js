migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "23k6mdvm",
    "name": "name",
    "type": "text",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "pattern": ""
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // remove
  collection.schema.removeField("23k6mdvm")

  return dao.saveCollection(collection)
})
