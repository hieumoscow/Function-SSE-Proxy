function updateAccumulatedCost(counterKey, currentCost, startDate, renewalPeriod, endDate, quota) {
  var collection = getContext().getCollection();
  var response = getContext().getResponse();
  var docId = counterKey;  // Use counterKey as the document ID

  // Parameter validation
  if (!counterKey) {
    throw new Error("counterKey is a required parameter");
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
      if (doc.endDate && now >= new Date(doc.endDate)) {
        throw new Error("Current time " + nowISO + " is at or after the end date " + doc.endDate);
      }

      // Check if we need to reset the accumulated cost due to renewal period
      var accumulatedCost = doc.accumulatedCost || 0;
      
      if (doc.renewalPeriod && doc.renewalStart) {
        var renewalPeriodMs = doc.renewalPeriod * 1000; // Convert seconds to ms
        var timeSinceRenewalStart = now.getTime() - doc.renewalStart;
        var renewalCycles = Math.floor(timeSinceRenewalStart / renewalPeriodMs);
        
        if (renewalCycles > 0) {
          // Reset accumulated cost if we've passed at least one renewal cycle
          accumulatedCost = 0;
          
          // Update the renewal start time to the beginning of the current period
          doc.renewalStart = doc.renewalStart + (renewalCycles * renewalPeriodMs);
        }
      }
      
      // Update accumulated cost
      accumulatedCost += currentCost;
      
      // Check if the accumulated cost exceeds the quota
      if (accumulatedCost > quota) {
        throw new Error("Accumulated cost " + accumulatedCost.toFixed(5) + " exceeded quota of " + quota);
      }
      
      // Update the document
      doc.accumulatedCost = accumulatedCost;
      doc.lastUpdated = nowISO;
      
      // If quota changed, update it
      if (doc.quota !== quota) {
        doc.quota = quota;
      }
      
      // If renewal period changed, update it and reset the renewal start time
      if (renewalPeriod && doc.renewalPeriod !== renewalPeriod) {
        doc.renewalPeriod = renewalPeriod;
        doc.renewalStart = now.getTime();
      }
      
      // If end date changed, update it
      if (endDate && doc.endDate !== new Date(endDate).toISOString()) {
        doc.endDate = new Date(endDate).toISOString();
      }
      
      // Replace the document
      var isReplaced = collection.replaceDocument(
        doc._self,
        doc,
        function (err, replacedDoc) {
          if (err) throw err;
          response.setBody(replacedDoc);
        }
      );
      
      if (!isReplaced) throw new Error("Failed to replace document");
    }
  );
  
  if (!isAccepted) throw new Error("Failed to read document");
}