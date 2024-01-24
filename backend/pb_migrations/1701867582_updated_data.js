migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("afv21ixeixtla5h")

  collection.name = "contents"

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("afv21ixeixtla5h")

  collection.name = "data"

  return dao.saveCollection(collection)
})
