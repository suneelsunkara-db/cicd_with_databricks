# Databricks notebook source
username = dbutils.notebook.entry_point.getDbutils().notebook().getContext().userName().get().replace('.','_')
user = username[:username.index("@")]
dbutils.widgets.text("source_dataset", "customers")

input_path = f'/FileStore/{username}_bronze_db/'
output_path = f'/FileStore/{username}_silver_db/'

# COMMAND ----------

from pyspark.sql.functions import *
from pyspark.sql.types import *
from pyspark.sql.window import Window
from delta.tables import *

# Define the start and end dates for each record in the dimension table
start_date = to_date(lit("2022-01-01"))
end_date = to_date(lit("9999-12-31"))

# Define the columns to include in the dimension table
dim_cols = ['customer_id', 'customer_name', 'state', 'company', 'phone_number', 'start_date', 'end_date']

def transform_to_scd2(customer_data):
  # Generate SCD Type 2 table
  
  silver_customers = DeltaTable.forName(spark, user+'_silver_db.silver_customers')
  effective_date = lit(current_date())
  scd2_data = customer_data.select(
      "customer_id",
      "customer_name",
      "state",
      "company",
      "phone_number"
  ).distinct().withColumn(
      "start_date",
      effective_date
  ).withColumn(
      "end_date",
      to_date(lit("9999-12-31"))
  )

  # Merge SCD Type 2 table with existing Delta Lake table
  merge_condition = "scd2.customer_id = source.customer_id"
  merge_delta_conf = {
      "mergeSchema": "true",
      "predicate": merge_condition
  }

  silver_customers.alias("scd2").merge(scd2_data.alias("source"),"scd2.customer_id = source.customer_id").whenMatchedUpdate(set={"end_date": date_sub(current_date(), 1)}).whenNotMatchedInsert(values={ "customer_id": col("source.customer_id"),"customer_name": col("source.customer_name"),"state": col("source.state"), "company": col("source.company"), "phone_number": col("source.phone_number"),"start_date": col("source.start_date"), "end_date": col("source.end_date")}).execute()

# COMMAND ----------

source_dataset_df = spark.read.format("delta").load(input_path+dbutils.widgets.get("source_dataset"))
transform_to_scd2(source_dataset_df)

# COMMAND ----------

# MAGIC %run ../setup/generate_retail_data

# COMMAND ----------

generate_customer_data_day_2()

# COMMAND ----------

# MAGIC %run ../bronze/load_data_into_bronze

# COMMAND ----------

# Set the target location for the delta table
target_path = f"/FileStore/{username}_bronze_db/"

load_data_to_bronze(dbutils.widgets.get("source_dataset"), target_path)

# COMMAND ----------

source_dataset_df = spark.read.format("delta").option("readChangeFeed", "true") \
  .option("startingVersion", 1) \
  .option("endingVersion", 2) \
  .load(input_path+"bronze_"+dbutils.widgets.get("source_dataset"))

transform_to_scd2(source_dataset_df)

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from shivam_panicker_silver_db.silver_customers where customer_id = 8999;
