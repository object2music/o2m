migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "v0zutziy",
    "name": "sort",
    "type": "text",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "pattern": ""
    }
  }))

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "1ezwox0d",
    "name": "duration",
    "type": "text",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "pattern": ""
    }
  }))

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "xm52hapa",
    "name": "discover",
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
  collection.schema.removeField("v0zutziy")

  // remove
  collection.schema.removeField("1ezwox0d")

  // remove
  collection.schema.removeField("xm52hapa")

  return dao.saveCollection(collection)
})
