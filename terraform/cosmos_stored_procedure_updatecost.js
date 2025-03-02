function updateAccumulatedCost(counterKey, model, currentCost, startDate, renewalPeriod, endDate, quota) {
  var collection = getContext().getCollection();
  var response = getContext().getResponse();
  var docId = model + "_" + counterKey;

  // Parameter validation
  if (!counterKey || !model) {
    throw new Error("counterKey and model are required parameters");
  }
  if (typeof currentCost !== "number" || currentCost < 0) {
    throw new Error("currentCost must be a non-negative number");
  }
  if (typeof quota !== "number" || quota <= 0) {
    throw new Error("quota must be a positive number");
  }
  if (renewalPeriod != null && typeof renewalPeriod !== "number") {
    throw new Error("renewalPeriod must be a number if provided");
  }

  // Read existing document or create new one if not found
  var isAccepted = collection.readDocument(
    collection.getAltLink() + "/docs/" + docId,
    function (err, doc) {
      var now = new Date();
      var nowISO = now.toISOString();
      var newDoc = err && err.number === 404 || !doc

      // If no document exists, create one.
      if (newDoc) {
        var effectiveStart = startDate ? new Date(startDate) : now;
        var newDoc = {
          id: docId,
          counterKey: counterKey,
          model: model,
          accumulatedCost: currentCost,
          startDate: effectiveStart.toISOString(),  // user-defined start date remains unchanged
          renewalPeriod: renewalPeriod || null,
          renewalStart: renewalPeriod ? effectiveStart.getTime() : null, // internal anchor for renewal
          endDate: endDate ? new Date(endDate).toISOString() : null,
          quota: quota,
          lastUpdated: nowISO
        };
        var isCreated = collection.createDocument(
          collection.getSelfLink(),
          newDoc,
          function (err, createdDoc) {
            if (err) throw err;
            response.setBody(createdDoc);
          }
        );
        if (!isCreated) throw new Error("Failed to create document");
        return;
      }

      // Document exists; use provided startDate if given, else use stored startDate.
      var effectiveStart = startDate ? new Date(startDate) : new Date(doc.startDate);
      if (now < effectiveStart) {
        throw new Error("Current time " + nowISO + " is before the start date " + effectiveStart.toISOString());
      }

      // Check end date; if current time is at or after the end date, reject the update.
      var effectiveEnd = endDate ? new Date(endDate) : (doc.endDate ? new Date(doc.endDate) : null);
      if (effectiveEnd && now >= effectiveEnd) {
        throw new Error("Current time " + nowISO + " is at or after the end date " + effectiveEnd.toISOString());
      }

      // Renewal logic: if a renewalPeriod is provided, update renewalStart and reset cost as needed.
      if (renewalPeriod || doc.renewalPeriod) {
        var period = renewalPeriod || doc.renewalPeriod; // in seconds
        var periodMs = period * 1000;
        // Initialize renewalStart if not set.
        if (!doc.renewalStart) {
          doc.renewalStart = effectiveStart.getTime();
        }
        
        // Calculate how many full periods have passed
        var timeSinceStart = now.getTime() - doc.renewalStart;
        if (timeSinceStart >= periodMs) {
          var completedPeriods = Math.floor(timeSinceStart / periodMs);
          doc.renewalStart += completedPeriods * periodMs;
          doc.accumulatedCost = 0;
        }
      }
      if (doc.accumulatedCost > quota) {
        throw new Error("Accumulated cost " + doc.accumulatedCost + " exceeded quota of " + quota);
      }

      // Accumulate current cost.
      var newTotal = (doc.accumulatedCost || 0) + currentCost;
      doc.accumulatedCost = newTotal;

      // Update document fields.
      doc.quota = quota;
      doc.lastUpdated = nowISO;
      if (startDate) {
        doc.startDate = new Date(startDate).toISOString();
      }
      if (renewalPeriod != null) {
        doc.renewalPeriod = renewalPeriod;
      }
      if (endDate) {
        doc.endDate = new Date(endDate).toISOString();
      }

      // Check if accumulated cost exceeds quota
      

      var isUpdated = collection.replaceDocument(
        doc._self,
        doc,
        function (err, updatedDoc) {
          if (err) throw err;
          response.setBody(updatedDoc);
        }
      );
      if (!isUpdated) throw new Error("Failed to update document");
    }
  );
  if (!isAccepted) throw new Error("Failed to read document");
}