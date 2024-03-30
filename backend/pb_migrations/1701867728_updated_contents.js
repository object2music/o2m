migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("afv21ixeixtla5h")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "prrpitgt",
    "name": "desc",
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
  const collection = dao.findCollectionByNameOrId("afv21ixeixtla5h")

  // remove
  collection.schema.removeField("prrpitgt")

  return dao.saveCollection(collection)
})
